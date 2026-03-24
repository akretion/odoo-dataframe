from odoo import models


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get("technical_name"):
            for rec in self:
                rec.display_name = f"{rec.field_description} ({rec.name})"
        return
