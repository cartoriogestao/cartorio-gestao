"""Comprovante de 30 dias: só após senha e TOTP, revogável e restrito a HTTPS."""
import re

import pytest

import dois_fatores as DF
import dois_fatores_dispositivos as DD
from bd_nativo import banco

SENHA = 'Senha#12345'
T0 = 1_800_000_000.0
HTTPS = 'https://localhost'


def csrf(r):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.get_data(as_text=True))[1]


def post(c, url, tela=None, base=HTTPS, **data):
    data['csrf_token'] = csrf(c.get(tela or url, base_url=base))
    return c.post(url, data=data, base_url=base)


def senha(c, base=HTTPS, username='mario', password=SENHA):
    return post(c, '/login', base=base, username=username, password=password)


@pytest.fixture
def casa(cg_casa, monkeypatch):
    db = cg_casa['db']
    uid = db.create_user('mario', 'Mario Exemplo dos Santos', SENHA, 'USER')
    tempo = [T0]
    monkeypatch.setattr(DF, 'relogio', lambda: tempo[0])
    with db.transaction() as con:
        segredo = DF.iniciar(con, uid, pasta=cg_casa['dados'])
        codigos = DF.confirmar(con, uid, DF.totp(segredo, T0), pasta=cg_casa['dados'], instante=T0)
    tempo[0] += 30
    return {**cg_casa, 'uid': uid, 'tempo': tempo, 'segredo': segredo, 'codigos': codigos}


def lembrar(casa, base=HTTPS, codigo=None, opt=True):
    c = casa['c']
    assert '/login/dois-fatores' in senha(c, base=base).location
    codigo = codigo or DF.totp(casa['segredo'], casa['tempo'][0])
    return post(c, '/login/dois-fatores', base=base, codigo=codigo,
                lembrar_dispositivo='1' if opt else '')


def sair(c):
    with c.session_transaction() as s:
        s.clear()


def test_lembra_somente_apos_totp_e_a_senha_continua_obrigatoria(casa):
    r = lembrar(casa)
    cookie = next(v for v in r.headers.getlist('Set-Cookie') if v.startswith(DD.COOKIE+'='))
    assert 'Max-Age=2592000' in cookie
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    assert 'Path=/' in cookie and 'Domain=' not in cookie
    token = casa['c'].get_cookie(DD.COOKIE).value
    with casa['db'].connect() as con:
        row = banco(con).um('SELECT * FROM dois_fatores_dispositivos')
        assert token not in repr(row)
    sair(casa['c'])
    assert '/login' in casa['c'].get('/', base_url=HTTPS).location
    assert '/login/dois-fatores' not in senha(casa['c']).location
    with casa['c'].session_transaction() as s:
        assert s['user_id'] == casa['uid'] and 'inicio' in s and 'last_activity' in s
    sair(casa['c'])
    assert '/login/dois-fatores' not in senha(casa['c'], password='incorreta').location
    with casa['c'].session_transaction() as s:
        assert not s.get('user_id')
    with casa['db'].connect() as con:
        logs = repr(banco(con).ler('SELECT action, details FROM audit_logs'))
    assert 'DISPOSITIVO_LEMBRADO' in logs and token not in logs
    assert DF.em_base32(casa['segredo']) not in logs


@pytest.mark.parametrize('caso', ['sem_opcao', 'recuperacao', 'http', 'reserva', 'codigo_errado'])
def test_nao_emite_fora_das_condicoes(casa, monkeypatch, caso):
    if caso == 'reserva':
        import modo_reserva as MRES
        monkeypatch.setattr(MRES, 'ativo', lambda: True)
    r = lembrar(casa, base='http://localhost' if caso == 'http' else HTTPS,
                codigo=casa['codigos'][0] if caso == 'recuperacao' else
                ('invalido' if caso == 'codigo_errado' else None), opt=caso != 'sem_opcao')
    assert not any(v.startswith(DD.COOKIE+'=') for v in r.headers.getlist('Set-Cookie'))
    with casa['db'].connect() as con:
        assert not banco(con).valor('SELECT count(*) FROM dois_fatores_dispositivos')


@pytest.mark.parametrize('mudanca', ['senha', 'papel', 'desativada', 'bloqueio', 'expirado', 'revogado', 'outro_usuario', 'forjado', 'rotacao_2fa', 'recuperacao_nova'])
def test_autorizacoes_invalidas_pedem_codigo(casa, mudanca):
    lembrar(casa)
    db, uid = casa['db'], casa['uid']
    token = casa['c'].get_cookie(DD.COOKIE).value
    with db.transaction() as con:
        bd = banco(con)
        if mudanca == 'senha':
            bd.escrever("UPDATE users SET password_hash = password_hash || 'x' WHERE id = %s", (uid,))
        elif mudanca == 'papel':
            bd.escrever("UPDATE users SET role = 'MANAGER' WHERE id = %s", (uid,))
        elif mudanca == 'desativada':
            bd.escrever('UPDATE users SET active = 0 WHERE id = %s', (uid,))
        elif mudanca == 'bloqueio':
            bd.escrever("UPDATE dois_fatores SET bloqueado_ate = '2999-01-01T00:00:00' WHERE user_id = %s", (uid,))
        elif mudanca == 'expirado':
            casa['tempo'][0] += DD.SEGUNDOS
        elif mudanca == 'revogado':
            DD.revogar(con, uid)
        elif mudanca == 'rotacao_2fa':
            DF.desativar(con, uid)
        elif mudanca == 'recuperacao_nova':
            DF.trocar_codigos(con, uid)
        elif mudanca == 'outro_usuario':
            uid += 1
        elif mudanca == 'forjado':
            token = 'a' * 43
    with db.connect() as con:
        assert not DD.confere(con, uid, token, agora=casa['tempo'][0], agora_iso=DF.agora_iso())


def test_nao_renova_prazo_nem_consulta_cookie_em_http_ou_reserva(casa, monkeypatch):
    lembrar(casa)
    c = casa['c']
    with casa['db'].connect() as con:
        validade = banco(con).valor('SELECT expira_em FROM dois_fatores_dispositivos')
    sair(c)
    casa['tempo'][0] += DD.SEGUNDOS - 1
    assert '/login/dois-fatores' not in senha(c).location
    with casa['db'].connect() as con:
        assert banco(con).valor('SELECT expira_em FROM dois_fatores_dispositivos') == validade
    sair(c)
    # Mesmo recebido de um cliente artificial, o cookie não dispensa TOTP em HTTP.
    assert '/login/dois-fatores' in senha(c, base='http://localhost').location
    sair(c)
    import modo_reserva as MRES
    monkeypatch.setattr(MRES, 'ativo', lambda: True)
    assert '/login/dois-fatores' in senha(c).location


def test_usuario_revoga_com_senha_e_codigo_e_formulario_tem_csrf(casa):
    lembrar(casa)
    c, db = casa['c'], casa['db']
    assert c.post('/conta/dois-fatores', data={}, base_url=HTTPS).status_code == 400
    r = post(c, '/conta/dois-fatores', senha='errada', codigo='invalido')
    with db.connect() as con:
        assert banco(con).valor('SELECT count(*) FROM dois_fatores_dispositivos') == 1
    casa['tempo'][0] += 30
    r = post(c, '/conta/dois-fatores', senha=SENHA,
             codigo=DF.totp(casa['segredo'], casa['tempo'][0]))
    with db.connect() as con:
        assert not banco(con).valor('SELECT count(*) FROM dois_fatores_dispositivos')
    assert 'Max-Age=0' in next(v for v in r.headers.getlist('Set-Cookie') if v.startswith(DD.COOKIE+'='))
    sair(c)
    assert '/login/dois-fatores' in senha(c).location


def test_limite_dez_e_mudanca_entre_conferencia_e_emissao(casa):
    db, uid = casa['db'], casa['uid']
    with db.transaction() as con:
        versao = DD.versao(con, uid)
        for i in range(12):
            assert DD.emitir(con, uid, esperada=versao, agora=T0+i)
        assert banco(con).valor('SELECT count(*) FROM dois_fatores_dispositivos') == 10
        banco(con).escrever("UPDATE users SET role='MANAGER' WHERE id=%s", (uid,))
        assert not DD.emitir(con, uid, esperada=versao, agora=T0+20)


@pytest.mark.parametrize('token', ['', 'x', 'a'*42, 'a'*44, '!'*43, None])
def test_formato_invalido_nao_consulta_banco(token):
    assert not DD.confere(None, 1, token, agora=T0, agora_iso='2027-01-15T08:00:00')
