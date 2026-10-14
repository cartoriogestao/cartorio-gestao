from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import date

from database import Database


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.sqlite3")
        self.uid = self.db.create_user("admin", "Administrador", "SenhaForte123", "ADMIN")

    def tearDown(self):
        self.tmp.cleanup()

    def test_auth(self):
        self.assertIsNotNone(self.db.authenticate("admin", "SenhaForte123"))
        self.assertIsNone(self.db.authenticate("admin", "errada"))

    def test_password_policy_default_is_six_without_complexity(self):
        uid = self.db.create_user("simples", "Usuário Simples", "abcdef", "USER")
        self.assertIsNotNone(self.db.authenticate("simples", "abcdef"))
        with self.assertRaises(ValueError):
            self.db.create_user("curta", "Senha Curta", "abcde", "USER")

    def test_password_policy_can_be_changed_in_settings(self):
        self.db.set_settings({
            "password_min_length": "4",
            "password_require_digit": "1",
        })
        with self.assertRaises(ValueError):
            self.db.create_user("semnumero", "Sem Número", "abcd", "USER")
        uid = self.db.create_user("comnumero", "Com Número", "abc1", "USER")
        self.assertIsNotNone(self.db.authenticate("comnumero", "abc1"))

    def test_inspection_seed_and_deadlines(self):
        iid = self.db.seed_inspection()
        tasks = [t for t in self.db.list_tasks(limit=2000) if t["inspection_id"] == iid]
        self.assertGreaterEqual(len(tasks), 70)
        self.assertTrue(all(t["due_date"] is None for t in tasks))
        self.db.set_inspection_start_date(iid, "2026-08-13", self.uid)
        tasks = [t for t in self.db.list_tasks(limit=2000) if t["inspection_id"] == iid]
        self.assertTrue(all(t["due_date"] for t in tasks))

    def test_expediente_protocol(self):
        eid = self.db.create_expediente({"source":"Malote Digital","subject":"Teste","category":"Para Cumprimento","received_at":"2026-08-12"}, self.uid)
        row = self.db.get_expediente(eid)
        self.assertTrue(row["internal_protocol"].startswith("EXP-"))

    def test_recurring_task(self):
        rid = self.db.create_recurrence({"title":"Rotina", "frequency":"MONTHLY", "next_due_date":date.today().isoformat(), "lead_days":5}, self.uid)
        self.assertEqual(self.db.ensure_recurring_tasks(), 1)
        self.assertTrue(any(t["recurrence_id"] == rid for t in self.db.list_tasks(limit=2000)))

    def test_checklist(self):
        template = self.db.list_checklist_templates()[0]
        run = self.db.start_checklist(template["id"], "REF", self.uid)
        _, items = self.db.get_checklist_run(run)
        self.db.save_checklist_run(run, {i["id"] for i in items}, {i["id"]:"" for i in items}, True)
        self.assertEqual(self.db.get_checklist_run(run)[0]["status"], "CONCLUIDO")


if __name__ == "__main__":
    unittest.main()
