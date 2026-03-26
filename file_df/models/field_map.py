from odoo import fields, models


class FieldMap(models.Model):
    _name = "field.map"
    _description = "Field mapping"
    _order = "field_id ASC"
    _rec_name = "field_id"
    _rec_names_search = ["field_id"]

    map_id = fields.Many2one(comodel_name="data.map", required=True, ondelete="cascade")
    sequence = fields.Integer()
    field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        ondelete="cascade",
        domain="[('model_id', '=', model_id), ('store', '=', True)]",
    )
    model_id = fields.Many2one(
        comodel_name="ir.model", related="map_id.model_id", readonly=True
    )
    name = fields.Char(
        required=True, help="Name field in the source file (spreadsheet)"
    )
    renamed = fields.Char(help="If specified, renamed to match with an odoo field")
    named = fields.Char(compute="_compute_named", help="Is renamed or name")
    useless = fields.Boolean(string="Skip", help="Field to exclude from the process")
    multi = fields.Boolean(help="Apply to multi values field")

    def _compute_named(self):
        for rec in self:
            rec.named = rec.renamed or rec.name
