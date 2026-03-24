from odoo import fields, models


class MatchingField(models.Model):
    _name = "matching.field"
    _description = "Fields referencing records"
    _rec_name = "model_id"
    _rec_names_search = ["model"]
    _order = "model_id"

    model_id = fields.Many2one(
        comodel_name="ir.model", ondelete="cascade", required=True
    )
    field_ids = fields.Many2many(comodel_name="ir.model.fields", required=True)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"{', '.join(rec.field_ids.mapped('name'))} ({rec.model_id.model})"
            )
