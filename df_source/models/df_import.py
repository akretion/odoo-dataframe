from odoo import api, exceptions, models


class DfImport(models.AbstractModel):
    _name = "df.import"
    _description = "Helper methods for ERP import"

    @api.model
    def _filter_useful_vals(self, model, vals):
        return {
            x: val
            for x, val in vals.items()
            if x.lower() in self.env[model]._fields.keys()
        }

    def _add_ir_model_data_safely(self, vals):
        """Check if name/module is already in ir.model.data"""
        for elm in ["name", "module", "model", "res_id"]:
            if elm not in vals:
                raise exceptions.ValidationError(f"Missing '{elm}' in vals {vals}")
        record = self.env["ir.model.data"].search(
            [("name", "=", vals["name"]), ("module", "=", vals["module"])]
        )
        if not record:
            return self.env["ir.model.data"].create(vals)
        return False

    def _check_base_import_match_config(self, model, field_keys=None):
        # TODO refactor
        def naive_check(match, field_keys=None):
            field_ = match.field_ids.filtered(
                lambda r: not r.conditional and not r.imported_value
            )
            if field_ and len(field_) == 1:
                if field_keys and field_.name in field_keys:
                    return field_.name
                else:
                    return field_.name
            return False

        if "base_import.match" not in self.env.registry.models.keys():
            # base_import_match module not installed
            return False
        matchs = self.env["base_import.match"].search([("model_id.model", "=", model)])
        ref_field = False
        for match in matchs:
            ref_field = naive_check(match, field_keys=field_keys)
            if ref_field:
                break
        return ref_field

    def _convert_flat_dict_to_ini(self, mydict):
        lines = []
        for key, val in mydict.items():
            if not val:
                val = ""
            lines.append(f"{key} = {val}")
        return "\n".join(lines)
