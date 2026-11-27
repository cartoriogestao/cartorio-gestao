// A CHAVE DA SUÍTE — o app da barra de menus (27/11/2026).
//
// Mostra quem está com a memória do servidor reserva (a suíte ou a IA local) e muda a
// chave. Ele só GRAVA o pedido (pedido.json, na pasta do dono); quem liga e desliga os
// serviços é o controlador (ci/chave/controlador.py, como root), que lê o pedido e
// publica o estado (estado.json). O app não tem privilégio nenhum.
//
// Montar: bash ci/chave/montar_app.sh
import AppKit
import SwiftUI

let PEDIDO = "/Users/Shared/CartorioGestao/chave-da-suite/pedido.json"
let ESTADO = "/Library/Application Support/CartorioGestao/chave-da-suite/estado.json"
let REPO = "cartoriogestao/cartorio-gestao"
let GH = "/opt/homebrew/bin/gh"
let NOMES_DOS_DIAS = ["S", "T", "Q", "Q", "S", "S", "D"]  // seg … dom (0 … 6)
let DIAS_POR_EXTENSO = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

// MARK: - Os arquivos

struct Janela: Codable, Identifiable, Equatable {
    var id = UUID()
    var dias: [Int]
    var inicio: String
    var fim: String
    enum CodingKeys: String, CodingKey { case dias, inicio, fim }
}

struct Pedido: Codable {
    var modo: String = "auto"
    var ate: Double? = nil
    var agenda: [Janela] = [Janela(dias: [0, 1, 2, 3, 4], inicio: "08:00", fim: "18:00")]
    var prioridade_ia: Bool? = nil
}

struct Estado: Decodable {
    var atualizado: String
    var modo: String
    var ate: Double?
    var agenda_texto: String
    var desejada: String
    var motivo: String
    var momento: String
    var vm_ligada: Bool
    var executor_ligado: Bool
    var suite_rodando: Bool
    var vm_gb: Double
    var proxima_troca: String?
    var aviso: String
    var ia_em_uso: Bool?
    var prioridade_ia: Bool?
}

func lerPedido() -> Pedido {
    guard let dados = FileManager.default.contents(atPath: PEDIDO),
          let p = try? JSONDecoder().decode(Pedido.self, from: dados) else { return Pedido() }
    return p
}

func gravarPedido(_ p: Pedido) throws {
    let codificador = JSONEncoder()
    codificador.outputFormatting = [.prettyPrinted, .sortedKeys]
    try codificador.encode(p).write(to: URL(fileURLWithPath: PEDIDO), options: .atomic)
}

func lerEstado() -> Estado? {
    guard let dados = FileManager.default.contents(atPath: ESTADO) else { return nil }
    return try? JSONDecoder().decode(Estado.self, from: dados)
}

/// Roda um programa fora da thread principal e devolve (código, saída).
func rodar(_ args: [String]) async -> (Int32, String) {
    await Task.detached {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: args[0])
        p.arguments = Array(args.dropFirst())
        let saida = Pipe()
        p.standardOutput = saida
        p.standardError = Pipe()
        do { try p.run() } catch { return (-1, "") }
        let dados = saida.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return (p.terminationStatus, String(decoding: dados, as: UTF8.self))
    }.value
}

func formatoHora(_ s: String) -> Date? {
    let f = DateFormatter()
    f.locale = Locale(identifier: "pt_BR")
    for formato in ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm"] {
        f.dateFormat = formato
        if let d = f.date(from: s) { return d }
    }
    return nil
}

func quando(_ d: Date) -> String {
    let cal = Calendar.current
    let hora = DateFormatter()
    hora.dateFormat = "HH:mm"
    if cal.isDateInToday(d) { return "hoje " + hora.string(from: d) }
    if cal.isDateInTomorrow(d) { return "amanhã " + hora.string(from: d) }
    let dia = (cal.component(.weekday, from: d) + 5) % 7  // domingo=1 -> 6
    return DIAS_POR_EXTENSO[dia] + " " + hora.string(from: d)
}

// MARK: - O modelo

@MainActor
final class Chave: ObservableObject {
    @Published var estado: Estado?
    @Published var pedido = lerPedido()
    @Published var fila: Int?
    @Published var mensagem = ""
    @Published var interrompendo = false
    private var relogio: Timer?
    private var relogioFila: Timer?

    init() {
        atualizar()
        relogio = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.atualizar() }
        }
        relogioFila = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.contarFila() }
        }
        Task { await contarFila() }
    }

    /// O modo que vale agora: um modo com prazo vencido volta a ser o automático.
    var modoValendo: String {
        if pedido.modo != "auto", let ate = pedido.ate, ate <= Date().timeIntervalSince1970 { return "auto" }
        return pedido.modo
    }

    var instalada: Bool { FileManager.default.fileExists(atPath: (PEDIDO as NSString).deletingLastPathComponent) }

    /// O controlador grava o estado a cada 5 s; mais de um minuto parado é problema.
    var controladorParado: Bool {
        guard let e = estado, let d = formatoHora(e.atualizado) else { return true }
        return Date().timeIntervalSince(d) > 60
    }

    func atualizar() {
        estado = lerEstado()
        pedido = lerPedido()
    }

    func contarFila() async {
        let (codigo, saida) = await rodar([GH, "run", "list", "-R", REPO, "-w", "suite", "-s", "queued",
                                           "--json", "databaseId", "-q", "length"])
        fila = codigo == 0 ? Int(saida.trimmingCharacters(in: .whitespacesAndNewlines)) : nil
    }

    func mudar(modo: String, horas: Double? = nil) {
        var p = lerPedido()
        p.modo = modo
        p.ate = horas.map { Date().timeIntervalSince1970 + $0 * 3600 }
        salvar(p)
    }

    func mudar(prioridade: Bool) {
        var p = lerPedido()
        p.prioridade_ia = prioridade
        salvar(p)
    }

    func salvar(agenda: [Janela]) {
        var p = lerPedido()
        p.agenda = agenda
        salvar(p)
    }

    private func salvar(_ p: Pedido) {
        do {
            try gravarPedido(p)
            pedido = p
            mensagem = ""
        } catch {
            mensagem = "Não consegui gravar o pedido: \(error.localizedDescription)"
        }
    }

    /// Cancela a suíte em andamento no GitHub e a põe de novo na fila: o executor fica
    /// livre, a chave desliga a VM, e a suíte roda quando a chave voltar para «suíte».
    func interromperSuite() async {
        interrompendo = true
        defer { interrompendo = false }
        let (codigo, saida) = await rodar([GH, "run", "list", "-R", REPO, "-w", "suite", "-s", "in_progress",
                                           "--json", "databaseId,displayTitle"])
        guard codigo == 0, let dados = saida.data(using: .utf8),
              let rodadas = try? JSONSerialization.jsonObject(with: dados) as? [[String: Any]] else {
            mensagem = "Não consegui falar com o GitHub (gh). Nada foi interrompido."
            return
        }
        var prs: [String] = []
        for r in rodadas {
            guard let id = r["databaseId"] as? Int else { continue }
            _ = await rodar([GH, "run", "cancel", String(id), "-R", REPO])
            if let titulo = r["displayTitle"] as? String, let n = titulo.split(separator: "#").last {
                prs.append(String(n).trimmingCharacters(in: .whitespaces))
            }
        }
        mensagem = "Suíte cancelada; esperando o executor sair do ar…"
        // Só devolve à fila depois que o executor saiu: senão ele pegaria a rodada de volta.
        for _ in 0..<90 {
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            atualizar()
            if let e = estado, !e.executor_ligado { break }
        }
        for pr in prs where !pr.isEmpty {
            _ = await rodar([GH, "workflow", "run", "suite.yml", "-R", REPO, "-f", "pr=\(pr)"])
        }
        mensagem = prs.isEmpty ? "" : "PR #\(prs.joined(separator: ", #")) voltou para a fila."
        await contarFila()
    }
}

// MARK: - A barra de menus

struct Rotulo: View {
    @ObservedObject var chave: Chave
    var body: some View {
        let (icone, texto) = Rotulo.aparencia(chave)
        HStack(spacing: 3) {
            Image(systemName: icone)
            Text(texto)
        }
    }

    static func aparencia(_ c: Chave) -> (String, String) {
        guard c.instalada else { return ("questionmark.circle", "Chave") }
        guard let e = c.estado, !c.controladorParado else { return ("exclamationmark.triangle", "Chave") }
        switch e.momento {
        case "suite": return ("testtube.2", "Suíte")
        case "ia": return ("brain", "IA")
        case "esperando": return ("hourglass", "→IA")
        case "ligando": return ("hourglass", "→Suíte")
        case "desligando": return ("hourglass", "→IA")
        default: return ("exclamationmark.triangle", "Chave")
        }
    }
}

struct Menu_: View {
    @ObservedObject var chave: Chave
    @Environment(\.openWindow) private var abrirJanela

    var body: some View {
        if !chave.instalada {
            Text("A chave não está instalada neste Mac.")
            Text("sudo bash ci/chave/instalar_chave.sh")
        } else if chave.controladorParado {
            Text("O controlador da chave não está respondendo.")
            Text("Veja /Library/Logs/CartorioGestao/chave-da-suite.log")
        }
        if let e = chave.estado {
            Text(situacao(e))
            Text(memoria(e))
            if e.motivo == "IA em uso (prioridade)" {
                Text("IA em uso, com prioridade: a suíte volta quando o modelo sair da memória")
            } else if let t = e.proxima_troca, let d = formatoHora(t) {
                Text("Muda para \(e.desejada == "ia" ? "a suíte" : "a IA") \(quando(d)) — \(e.motivo)")
            } else {
                Text(e.motivo)
            }
            if e.ia_em_uso == true { Text("IA em uso: há modelo carregado no Ollama") }
            if !e.aviso.isEmpty { Text("⚠︎ " + e.aviso) }
        }
        if !chave.mensagem.isEmpty { Text(chave.mensagem) }
        Divider()
        Toggle("Automático (agenda)", isOn: modo("auto"))
        Toggle("Suíte sempre", isOn: modo("suite"))
        Toggle("IA sempre", isOn: modo("ia"))
        Toggle("IA tem prioridade quando estiver em uso", isOn: Binding(
            get: { chave.pedido.prioridade_ia == true },
            set: { chave.mudar(prioridade: $0) }))
        Menu("IA agora, por…") {
            ForEach([1.0, 2.0, 4.0, 8.0], id: \.self) { h in
                Button("\(Int(h)) h") { chave.mudar(modo: "ia", horas: h) }
            }
        }
        Menu("Suíte agora, por…") {
            ForEach([1.0, 2.0, 4.0, 8.0], id: \.self) { h in
                Button("\(Int(h)) h") { chave.mudar(modo: "suite", horas: h) }
            }
        }
        if chave.estado?.momento == "esperando" {
            Button(chave.interrompendo ? "Interrompendo a suíte…" : "Interromper a suíte agora…") {
                confirmarInterrupcao()
            }.disabled(chave.interrompendo)
        }
        Divider()
        Button("Agenda da IA…") {
            abrirJanela(id: "agenda")
            NSApp.activate(ignoringOtherApps: true)
        }
        Button("Abrir as suítes no GitHub") {
            NSWorkspace.shared.open(URL(string: "https://github.com/\(REPO)/actions/workflows/suite.yml")!)
        }
        Divider()
        Button("Sair do app (a chave continua valendo)") { NSApp.terminate(nil) }
    }

    func modo(_ m: String) -> Binding<Bool> {
        Binding(get: { chave.modoValendo == m }, set: { if $0 { chave.mudar(modo: m) } })
    }

    func situacao(_ e: Estado) -> String {
        switch e.momento {
        case "suite": return e.suite_rodando ? "Suíte ligada — rodando uma suíte agora" : "Suíte ligada — executor livre"
        case "ia": return "IA com a memória — a VM da suíte está desligada"
        case "esperando": return "Esperando a suíte em andamento terminar para liberar a IA"
        case "ligando": return "Ligando a VM e o executor da suíte…"
        case "desligando": return "Desligando o executor e a VM…"
        default: return "Situação: " + e.momento
        }
    }

    func memoria(_ e: Estado) -> String {
        let vm = e.vm_ligada ? String(format: "VM %.1f GB", e.vm_gb).replacingOccurrences(of: ".", with: ",")
                             : "VM desligada"
        let fila = chave.fila.map { $0 == 1 ? "1 suíte na fila" : "\($0) suítes na fila" } ?? "fila: ?"
        return vm + " · " + fila
    }

    func confirmarInterrupcao() {
        let alerta = NSAlert()
        alerta.messageText = "Interromper a suíte em andamento?"
        alerta.informativeText = "A rodada é cancelada no GitHub e volta para a fila; ela roda de novo, do começo, quando a chave voltar para a suíte. Até lá o PR fica com o status «suite» vermelho («a suíte não terminou»)."
        alerta.addButton(withTitle: "Interromper")
        alerta.addButton(withTitle: "Esperar terminar")
        NSApp.activate(ignoringOtherApps: true)
        if alerta.runModal() == .alertFirstButtonReturn {
            Task { await chave.interromperSuite() }
        }
    }
}

// MARK: - A janela da agenda

final class EditorDaAgenda: ObservableObject {
    @Published var janelas: [Janela] = []
    @Published var salvo = false
    func recarregar() { janelas = lerPedido().agenda; salvo = false }
}

struct LinhaDaJanela: View {
    @Binding var janela: Janela
    var tirar: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 2) {
                ForEach(0..<7, id: \.self) { d in
                    Toggle(NOMES_DOS_DIAS[d], isOn: dia(d)).toggleStyle(.button).help(DIAS_POR_EXTENSO[d])
                }
            }
            DatePicker("das", selection: hora(\.inicio), displayedComponents: .hourAndMinute)
            DatePicker("às", selection: hora(\.fim), displayedComponents: .hourAndMinute)
            Button(action: tirar) { Image(systemName: "trash") }.help("Tirar esta janela")
        }
    }

    func dia(_ d: Int) -> Binding<Bool> {
        Binding(get: { janela.dias.contains(d) }, set: { liga in
            var dias = Set(janela.dias)
            if liga { dias.insert(d) } else { dias.remove(d) }
            janela.dias = dias.sorted()
        })
    }

    func hora(_ campo: WritableKeyPath<Janela, String>) -> Binding<Date> {
        Binding(get: {
            let partes = janela[keyPath: campo].split(separator: ":").compactMap { Int($0) }
            let h = partes.first ?? 0
            let m = partes.count > 1 ? partes[1] : 0
            return Calendar.current.date(bySettingHour: h, minute: m, second: 0, of: Date()) ?? Date()
        }, set: { d in
            let c = Calendar.current.dateComponents([.hour, .minute], from: d)
            janela[keyPath: campo] = String(format: "%02d:%02d", c.hour ?? 0, c.minute ?? 0)
        })
    }
}

struct Agenda: View {
    @ObservedObject var chave: Chave
    @ObservedObject var editor: EditorDaAgenda

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Janelas da IA").font(.headline)
            Text("Nestas horas a suíte cede a memória à IA: a suíte em andamento termina, a VM desliga e as próximas esperam na fila. Fora delas a suíte roda. Uma janela que atravessa a meia-noite conta pelo dia em que começa.")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            ForEach($editor.janelas) { $j in
                LinhaDaJanela(janela: $j) { tirar(j.id) }
            }
            if editor.janelas.isEmpty {
                Text("Sem janela: no automático, a suíte fica com a memória o tempo todo.").foregroundStyle(.secondary)
            }
            HStack {
                Button("Adicionar janela") {
                    editor.janelas.append(Janela(dias: [0, 1, 2, 3, 4], inicio: "12:00", fim: "14:00"))
                    editor.salvo = false
                }
                Spacer()
                if editor.salvo { Text("Salvo").foregroundStyle(.secondary) }
                Button("Salvar", action: salvar).keyboardShortcut(.defaultAction)
            }
            if !chave.mensagem.isEmpty { Text(chave.mensagem).foregroundStyle(.red) }
        }
        .padding(20)
        .frame(minWidth: 560)
        .onAppear { editor.recarregar() }
    }

    func tirar(_ id: UUID) {
        editor.janelas.removeAll { $0.id == id }
        editor.salvo = false
    }

    func salvar() {
        let validas = editor.janelas.filter { !$0.dias.isEmpty && $0.inicio != $0.fim }
        chave.salvar(agenda: validas)
        editor.janelas = validas
        editor.salvo = chave.mensagem.isEmpty
    }
}

// MARK: - O app

@main
struct ChaveDaSuiteApp: App {
    @StateObject private var chave = Chave()
    @StateObject private var editor = EditorDaAgenda()

    var body: some Scene {
        MenuBarExtra {
            Menu_(chave: chave)
        } label: {
            Rotulo(chave: chave)
        }
        .menuBarExtraStyle(.menu)

        Window("Agenda da IA", id: "agenda") {
            Agenda(chave: chave, editor: editor)
        }
        .windowResizability(.contentSize)
    }
}
