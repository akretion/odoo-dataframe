from odoo import _, exceptions, fields, models

# You can store files .sql in this relative path of your module
DF_RELATIVE_SRC_DIR = "data/df"

MODULE = __name__[12 : __name__.index(".", 13)]


class DfSource(models.Model):
    _inherit = "df.source"

    map_id = fields.Many2one(comodel_name="data.map", ondelete="cascade")
    comment = fields.Html(help="Fail or manual message")
    comment_short = fields.Html(
        string="Comment",
        compute="_compute_comment_short",
        help="Comment field short version for list view",
    )

    def _compute_comment_short(self):
        for rec in self:
            if rec.comment:
                if "…" in rec.comment:
                    rec.comment_short = rec.comment[: rec.comment.index("…") + 1]
                else:
                    rec.comment_short = rec.comment[:30]
            else:
                rec.comment_short = False

    def _process(self):
        action = super()._process()
        if self.map_id:
            action = self._file_process()
        elif "df.query" not in self.env.registry.models.keys():  # pragma: no cover
            raise exceptions.UserError(
                _("Please complete Map column to ensure a file processing ...")
            )
        return action

    def _file_process(self):
        vals = {
            "filename": self.name,
            "file": self.file,
            "source_id": self.id,
            "map_id": self.map_id.id,
        }
        res = self.env["df.file.wiz"].create(vals)
        if isinstance(res, dict):
            # res is an Odoo action (i.e. df.source when fail)
            return res  # pragma: no cover
        if self.name.lower().endswith((".csv", ".ods", ".xlsx")):
            wiz_action = self.env.ref(f"{MODULE}.df_file_wiz_action")._get_action_dict()
            wiz_action["res_id"] = res.id
            return wiz_action
        return self.env.ref(
            "df_source.df_source_action"
        )._get_action_dict()  # pragma: no cover
