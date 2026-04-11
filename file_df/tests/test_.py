import base64
from pathlib import Path

from odoo_test_helper import FakeModelLoader

from odoo import exceptions
from odoo.modules.module import get_module_path
from odoo.tests.common import TransactionCase

MODULE = __name__[12 : __name__.index(".", 13)]


class Test(TransactionCase):
    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        from .fake_model import DataMap, ResPartner

        self.loader.update_registry((ResPartner, DataMap))

        self.module = self.env["df.source"]._get_uidstring_module_name()
        self.demo_map = self.env.ref("__.hello_data_map")
        # demo entry is set after fake model instanciation
        self.demo_map.transformation = "demo"
        self.demo_map.field_ids.filtered(lambda r: r.name == "Town").multi = True
        self.demo_map.multi_value_id = (
            self.env["ir.model.fields"]
            .search([("model", "=", "res.partner"), ("name", "=", "my_json")])
            .id
        )

    def tearDown(self):
        self.loader.restore_registry()
        super().tearDown()

    def test_demo_data(self):
        wiz = get_wizard(self, "hello")
        wiz.with_context(controller="_process").apply()
        ak = self.env.ref(f"{self.module}.demo_datamap_1Akretion")
        assert ak.color == 10
        assert ak.my_toml == "Town = Lyon"

    def test_insert_csv(self):
        d_map = self.env["data.map"]._add_demo_data(name="new")
        d_map.file = base64.b64encode(
            b"Country;name;Town;Street\n" + b"France;Akretion;Lyon;rue de l'arbre sec\n"
        )
        d_map.serialize_config()
        assert d_map.config == "{'renamed': {'Country': 'country_id'}}"
        # marginal checks
        # below lines must be moved to db_process module
        d_map.source_id.name = "hello /odoo/links/ any"
        assert d_map.source_id.short_name == "hello  any"

    def test_insert_file(self):
        def insert_file(name):
            d_map = self.env["data.map"]._add_base_data(name=name)
            filename = f"hello_file.{name}"
            path = Path(get_module_path(MODULE)) / "tests" / filename
            with open(path, "rb") as f:
                d_map.file_name = filename
                d_map.file = base64.b64encode(f.read())
                assert d_map.file
                assert d_map.file_name == filename

        insert_file("xlsx")
        insert_file("ods")

    def test_demo_wizard(self):
        self.demo_map.multi_value_id = (
            self.env["ir.model.fields"]
            .search([("model", "=", "res.partner"), ("name", "=", "my_json")])
            .id
        )
        wiz = get_wizard(self, "hello")
        wiz.with_context(controller="_download").apply()
        wiz = get_wizard(self, "hello")
        wiz.with_context(controller="_process").apply()
        ak = self.env.ref(f"{self.module}.demo_datamap_1Akretion")
        assert ak.my_json == '{"Town":"Lyon"}'
        assert ak.my_toml == "Town = Lyon"

    def test_field_display_name(self):
        assert (
            self.demo_map.with_context(technical_name=1)
            .field_ids[1]
            .field_id.display_name
            == "Name (name)"
        )

    def test_serialization(self):
        with self.assertRaises(exceptions.ValidationError):
            self.demo_map.config = ";;-weird syntax!/"
        # syntax ok
        self.demo_map.config = '{"valid_key": 1}'

    def test_code(self):
        self.demo_map.transformation = "demo"
        # check that methods code appears in interface
        assert "_df_alter_demo(" in self.demo_map.expression
        assert "_df_alter_demo_other_method(" in self.demo_map.expression

    def test_scenari(self):
        # TODO improve
        self.env["data.map"]._add_demo_data(name="hello")
        wiz = get_wizard(self, "hello")
        assert wiz.scenari_explained == ""

    def test_workflow(self):
        dmap = self.demo_map
        self.env["data.map"]._add_demo_data(name="hello")
        wiz = get_wizard(self, "hello")
        wiz.with_context(controller="_process").apply()
        src = dmap.source_id
        assert src.state == "done"
        assert src.count == 3
        wiz = get_wizard(self, "hello")
        wiz.with_context(controller="_process").apply()
        # source have been duplicated
        assert src != dmap.source_id
        dmap.validate()
        dmap.reset()
        dmap.validate()
        dmap.close()

    def test_improbable(self):
        "Improbable use cases but that should not break the system"
        res = self.demo_map.copy()
        assert res.code == "hello (copy)"
        self.demo_map.unlink()


def get_wizard(self, name):
    dmap = self.env["data.map"].search([("code", "=", name)])
    action = dmap.start()
    return self.env["df.file.wiz"].browse(action.get("res_id"))
