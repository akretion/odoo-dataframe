from odoo import _, fields, models
from odoo.exceptions import UserError


class FieldLog(models.Model):
    _name = "field.log"
    _description = "Logs on field records"

    field_id = fields.Many2one(comodel_name="ir.model.fields")
    model_id = fields.Many2one(
        string="model_id", comodel_name="ir.model", related="field_id.model_id"
    )
    model = fields.Char(related="model_id.model", store=True)
    info = fields.Text(help="Exception message")
    data = fields.Text(help="Data in the context of the log")
    res_id = fields.Integer(help="Record ID in the model_ref")
    ref_model = fields.Char(help="Model in the current ERP of related record")
    kind = fields.Text(help="Log typology allowing to filter logs")

    def _log(self, model, info, field=None, res_id=None, data=None, kind=None):
        module = self.env[model]._fields["id"]._module
        table = model.replace(".", "_")
        if field:
            field = self.env.ref(f"{module}.field_{table}__{field}")
        else:
            field = self.env.ref(f"{module}.field_{table}__id")
        return self.env["field.log"].create(self._prepare_data(field, info, data, kind))

    def _fields_to_add(self):
        return ["res_id", "ref_model"]

    def _prepare_data(self, field, info, data, kind):
        """Prepare data for logging"""
        res = {}
        for elm in self._fields_to_add():
            res[elm] = data.get(elm) and data.pop(elm) if data else None
        res.update(
            {
                "field_id": field.id,
                "info": info,
                "data": f"{data}",
                "kind": kind,
            }
        )
        return res

    def goto_current_erp(self):
        self.ensure_one()
        if not self.res_id:
            raise UserError(_("Missing 'res_id' field to navigate to the current ERP "))
        return {
            "name": _("Related"),
            "res_model": self.ref_model,
            "view_mode": "list,form",
            "domain": [("id", "=", self.res_id)],
            "type": "ir.actions.act_window",
            "target": "current",
        }

    def get_res_id(self):
        "Called from ui"
        return self._get_field_id("res_id")

    def _get_field_id(self, ttype):
        message = f"{ttype}: {[x for x in sorted(self.mapped(ttype)) if x]}"
        ffield = "model"
        model = list(set([x for x in self.mapped(ffield) if x]))
        if model:
            message += f" | Model: {model}"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"Selected '{ttype}' field",
                "type": "info",  # warning/success
                "message": message,
                "sticky": True,
            },
        }

    def _unlink_logs_from_unlinked_resources(self, model, res_ids):
        self.search([("model", "=", model), ("res_id", "in", res_ids)]).unlink()
