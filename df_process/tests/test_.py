import polars as pl

from odoo.tests.common import TransactionCase

MODULE = __name__[12 : __name__.index(".", 13)]


class Test(TransactionCase):
    def setUp(self):
        super().setUp()
        self.module = self.env["df.source"]._get_uidstring_module_name()
        self.source = self.env["df.source"].create(
            {
                "model": "res.partner",
                "name": "hello",
            }
        )
        data = {
            "name": ["Akretion", "Achimanapse", "Larry_the_cat"],
            "industry_id": ["base.res_partner_industry_J", None, None],
            "street": ["rue de l'arbre sec", "rue de ...", "10 downing street"],
            "write_date": ["24/01/2029", "12/06/2028", "07/11/2023"],
        }
        self.df = pl.DataFrame(data)

    def test_only_create(self):
        created_records, updated_records = self.env["df.import"]._odoo_df_upsert(
            self.df, self.source
        )
        # check m2o transformation
        assert created_records.filtered(
            lambda r: r.industry_id
        ).industry_id == self.env.ref("base.res_partner_industry_J")
        # all records should be created, no update
        assert len(created_records) == 3
        assert not updated_records

    def test_create_and_update(self):
        record = self.env["res.partner"].create({"name": "hello"})
        self.env["upsert.mixin"]._add_ir_model_data(
            record, "Akretion", self.env["df.source"]._get_uidstring_module_name()
        )
        # the uidstring should be "Akretion"
        assert record.get_metadata()[0]["xmlid"][9:] == "Akretion"
        # we name 'id' as 'name' column
        df = self.df.with_columns(pl.col("name").alias("id"))
        created_records, updated_records = self.env["df.import"]._odoo_df_upsert(
            df, self.source
        )
        # 2 records should be created, 1 updated
        assert created_records and len(created_records) == 2
        assert updated_records and len(updated_records) == 1
