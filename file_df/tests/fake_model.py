import polars as pl

from odoo import fields, models
from odoo.tools.safe_eval import safe_eval


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = "res.partner"
    _description = "Fake Model"

    my_json = fields.Json(
        copy=False,
        inverse="_inverse_clean_data",
    )
    my_toml = fields.Text(
        compute="_compute_toml_like",
        copy=False,
        readonly=True,
    )
    df_ref = fields.Reference(
        string="Source",
        ondelete="set null",
        copy=False,
        selection=[("df.source", "Df Source")],
        help="Keep track of the source of the data, for data imported from file",
    )

    def _compute_toml_like(self):
        for rec in self:
            if rec.my_json:
                rec.my_toml = self.env["df.import"]._convert_flat_dict_to_ini(
                    safe_eval(rec.my_json)
                )
            else:
                rec.my_toml = False  # pragma: no cover

    def _inverse_clean_data(self):
        # TODO make it generic
        for rec in self:
            rec.my_json = rec.my_json.replace("\\", "").replace("null", "''")


class DataMap(models.Model):
    _name = "data.map"
    _inherit = "data.map"
    _description = "Fake Model"

    transformation = fields.Selection(selection_add=[("demo",) * 2])

    def _df_alter_demo(self, df):
        demo = self.env.ref("__.hello_data_map", raise_if_not_found=False)
        # only for demo case
        if self.transformation == "demo":
            if demo and self == demo:
                self._check_missing_cols(
                    df, ["country_id", "name", "Town", "street", "color"]
                )
                #  create xmlid
                df = df.with_columns(
                    (pl.lit("demo_datamap_1") + pl.col("name")).alias("id")
                )
                countries = self._demo_dataframe()
                # substitute colors by numbers
                df = df.with_columns(pl.col("color").replace(COLORS).alias("color"))
                # substitute country names by codes
                df = df.with_columns(
                    pl.col("country_id").replace(countries).alias("country_id")
                )
        return df

    def _df_alter_demo_other_method(self, df):
        "Only to check is this method is discovered"
        return df

    def _demo_dataframe(self):
        countries = {
            x.name: x.code.lower() if x.code != "GB" else "uk"
            for x in self.env["res.country"].search(
                [("name", "in", ("France", "Belgium", "United Kingdom"))]
            )
        }
        return {name: f"base.{code}" for name, code in countries.items()}


COLORS = {
    "red": 1,
    "orange": 2,
    "yellow": 3,
    "blue": 4,
    "purple": 5,
    "brown": 6,
    "cyan": 7,
    "purple2": 8,
    "pink": 9,
    "green": 10,
    "mauve": 11,
}
