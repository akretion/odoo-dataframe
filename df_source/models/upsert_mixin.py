import logging

from psycopg2.errors import IntegrityError

from odoo import _, models
from odoo.exceptions import ValidationError

PREFIX = "any"
# Copied from odoo/addons/base/tests/common.py
OVERRIDE_CONTEXT = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_create_nosubscribe": True,
    "mail_notrack": True,
    "no_reset_password": True,
    "create_by_dataframe": True,
}
EXCEPTIONS = {
    "uom.uom": ("UoM category Unit should only have one reference unit of measure.",)
}

logger = logging.getLogger(__name__)


class UpsertMixin(models.AbstractModel):
    _name = "upsert.mixin"
    _description = "Allow to insert ou update records"

    def get_id_strings(self, module=None):
        if not module:
            module = self.env["df.source"]._get_uidstring_module_name()
        return {
            x.name: x.model
            for x in self.env["ir.model.data"].search([("module", "=", module)])
        }

    def _no_idstring_case(self, model, values):
        """Case where you have base_import_match installed
        and configured with current model
        Need to check that a field in values is matching
        with a field in base_import_match
        """
        ref_field = self.env["df.import"]._check_base_import_match_config(
            model, values.keys()
        )
        if ref_field:
            record = self.env[model].search([(ref_field, "=", values[ref_field])])
            if record and record[0]:
                record[0].update(values)
                if len(record) > 1:
                    logger.warning(
                        f"More than 1 record found for {model} with "
                        + f"{ref_field}={values[ref_field]}: {record}"
                    )
                return record[0]
            else:
                return self.env[model].create(values)
        else:
            raise ValidationError(
                _(
                    "Missing 'id' field in values and no base_import_match "
                    + f"configured for model {model}.\n"
                    + f"Here is sample of values\n\n{values}"
                )
            )

    def _upsert_record(self, model, id_string, values, module=None):
        """Create or update a record matching xmlid with values
        Code from Anthem lib
        """
        # pylint: disable=C901
        if not module:
            module = self.env["df.source"]._get_uidstring_module_name()
        error = False
        if not id_string:
            record = self._no_idstring_case(model, values)
            return record, False, error
        if "." in id_string:
            module, id_string = id_string.split(".")
        if isinstance(model, str):
            model = self.env(context=dict(self.env.context, **OVERRIDE_CONTEXT))[model]
        record = self.env.ref(f"{module}.{id_string}", raise_if_not_found=False)
        if record:
            record.update(values)
        else:
            try:
                # TODO debug
                # useful_vals = self.env["df.import"]._filter_useful_vals(model, values)
                # record = model.create(useful_vals)
                record = model.create(values)
                logger.info(f"\n\n{record.id} {record}")
            except IntegrityError as err:
                return False, False, err
            except Exception as err:
                record = False
                # TODO refactor or return raise
                error_name = err.__str__()
                if EXCEPTIONS.get(model._name):
                    for exception in EXCEPTIONS[model._name]:
                        if error_name == _(exception):
                            if hasattr(
                                self.env[model._name],
                                "_get_back_record_after_df_exception",
                            ):
                                record = self.env[
                                    model._name
                                ]._get_back_record_after_df_exception(exception, values)
                if record:
                    record = record[0]
                    self._add_ir_model_data(record, id_string, module)
                else:
                    error = (
                        "Error \n"
                        + error_name
                        + "\nUniqueIDString "
                        + id_string
                        + ": "
                        + str(values)
                    )
                    logger.critical(error)
            if record:
                self._add_ir_model_data(record, id_string, module)
        return record, id_string, error

    def _add_ir_model_data(self, record, id_string, module, noupdate=False):
        """Add a XMLID on an existing record"""
        ref_id = self.env.ref(f"{module}.{id_string}", raise_if_not_found=False)
        if ref_id:
            return self.env["ir.model.data"].browse(ref_id)
        ImData = self.env["ir.model.data"].search(
            [("module", "=", module), ("name", "=", id_string)]
        )
        if ImData:
            ids = [int(x.split(",")[1]) for x in ImData.mapped("reference")]
            rec = self.env[ImData.model].browse(ids[0])
            message = f"Existing record '{rec.display_name}, id {rec.id}, {rec._name}'"
            message += f" with this id_string: {id_string} module: {module}\n"
            message += "Probably an orphelin XmlID !"
        return self.env["ir.model.data"].create(
            {
                "name": id_string,
                "module": module,
                "model": record._name,
                "res_id": record.id,
                "noupdate": noupdate,
            }
        )
