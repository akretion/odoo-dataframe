import math
import time
from pathlib import Path

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.modules.module import get_module_path

from ..classes.spreadsheet import Df2Spreadsheet

# You can store files .sql in this relative path of your module
DF_RELATIVE_SRC_DIR = "data/df"
MODULE = __name__[12 : __name__.index(".", 13)]


class DfSource(models.Model):
    _name = "df.source"
    _description = "Dataframe data source"

    _rec_name = "file_name"
    _rec_names_search = ["name"]
    _order = "sequence, file_name, id"

    def _default_sequence(self):
        cat = self.search([], limit=1, order="sequence DESC")
        if cat:
            return cat.sequence + 5
        return 10000

    model = fields.Text(
        default="res.partner", required=True, index=True, help="Odoo model name"
    )
    # TODO rename full path
    name = fields.Char(default="_", help="Supported files: .xlsx")
    short_name = fields.Text(compute="_compute_other_names", store=True)
    file_name = fields.Text(compute="_compute_other_names", store=True)
    time = fields.Integer(readonly=True, help="Execution time in seconds (rounded up)")
    count = fields.Integer(readonly=True, string="#", help="Records count")
    sequence = fields.Integer(default=_default_sequence, index=True)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="draft",
    )
    readonly = fields.Boolean(help="Imported records from module are readonly created")
    linked = fields.Boolean(help="Some odoo records are linked to this source")
    file = fields.Binary(attachment=False)
    filename = fields.Char(readonly=True)

    def start(self):
        self.ensure_one()
        start_time = time.time()
        if not self.env.context.get("clause_model") and self.state == "done":
            raise ValidationError(
                _("Switch to 'Draft' state to trigger another import")
            )
        action = self._process()
        end_time = time.time()
        # Calculate elapsed time
        self.time = math.ceil(end_time - start_time)
        return action

    def _process(self):
        self.ensure_one()
        return False

    def _save_in_spreadsheet(self, df):
        self.ensure_one()
        name = self.name
        if hasattr(self, "query_id"):
            # Called from db_process module
            name = self.query_id.name
        self.filename = f"{name}.xlsx"
        self.file = Df2Spreadsheet._get_spreadsheet_from_df(df)

    def save_in_xlsx(self):
        """Store dataframe in xlsx file"""
        if self and len(self) > 1:
            raise ValidationError(
                _("Can't save in xlsx file when source has more than one record.")
            )
        self.with_context(output="xlsx")._process()

    @api.depends("name")
    def _compute_other_names(self):
        for rec in self:
            short = rec.name
            for elm in self._subsitute_in_name():
                if elm in short:
                    short = short.replace(elm, "")
            rec.short_name = short
            rec.file_name = rec.name[rec.name.rfind("/") + 1 :]

    def _subsitute_in_name(self):
        return ["/odoo/links/", "/odoo/local-src/"]

    @staticmethod
    def _get_uidstring_module_name():
        # akretion à l'envers
        return "noiterka"

    def goto_records(self):
        """Goto records created from current df.source"""
        self.ensure_one()
        model_rec = self.env["ir.model"].search([("model", "=", self.model)], limit=1)
        if self.linked:
            return {
                "name": _(f"Imported records '{model_rec.name}'"),
                "res_model": model_rec.model,
                "view_mode": "list,form",
                # TODO fix _get_records() call
                "domain": [("id", "in", self._get_records(model_rec).ids)],
                "type": "ir.actions.act_window",
                "target": "current",
            }

    def reset_process(self):
        # TODO fix 'uom_cat.sql' case
        self.ensure_one()
        res = self._reset_process()
        if isinstance(res, dict):
            # res is a client action
            return res
        message = f"{self.model or ''}"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Reset process",
                "type": "success",
                "message": message,
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _reset_process(self):
        "Inherit me"
        self._get_records().unlink()
        self.linked = False
        self.state = "draft"

    def _populate(self):
        "Create/Update in current model, module files in DF_RELATIVE_SRC_DIR"
        action = self.env.ref(f"{MODULE}.df_source_action")._get_action_dict()
        return action

    def _get_records(self):
        self.ensure_one()
        # TODO
        return self.env[self.model].search([("df_source_id", "=", self.id)])

    def _get_files_in_modules(self, relative_path, extension=None):
        files = {}
        # Search all modules with df .sql files
        addons = self._get_modules_with_df_sql_files()
        # Sort module by dependency
        self.env.cr.execute(
            """
            SELECT  m.name
            FROM ir_module_module_dependency d
                LEFT JOIN ir_module_module m ON m.id = d.module_id
            WHERE m.state = 'installed'
            GROUP BY m.name
            ORDER BY max(d.id) ASC
        """
        )
        addons = [x[0] for x in self.env.cr.fetchall() if x[0] in addons]
        for addon in addons:
            path = Path(get_module_path(addon)) / relative_path
            if not path.is_dir():
                # directory is empty
                continue
            for file in path.iterdir():
                if file.is_file():
                    if extension:
                        if file.name[-len(extension) :] != extension:
                            continue
                    # File name is unique (the last replace the previous one)
                    files[file.parts[-1]] = file
        return files.values()

    def _get_file(self, name=None):
        # TODO Clean
        if self.template:
            # template is base64 data
            return self.template
        addon, file = self._get_addon_and_file_from_source_name()
        name = self.name or name
        path = Path(get_module_path(addon))
        path = path / DF_RELATIVE_SRC_DIR / file
        with open(path, "rb") as f:
            return f.read()

    def _get_modules_with_df_sql_files(self):
        """
        You may override if you want populate files in your module
        returns:
            ["module_name", "module2"]
        """
        return []

    def _get_addon_and_file_from_source_name(self):
        addon = self.name[: self.name.find("/")]
        file = self.name[self.name[::-1].find("/") :]
        return addon, file
