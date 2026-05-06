import base64
import io
import re
from string import Template

import polars as pl

from odoo import _, fields, models
from odoo.tools.safe_eval import safe_eval


class DfFileWiz(models.TransientModel):
    _name = "df.file.wiz"
    _description = "Process Polars DataFrame from file"
    _rec_name = "map_id"

    map_id = fields.Many2one(comodel_name="data.map", required=True)
    comment = fields.Text(related="map_id.comment", readonly=True)
    check = fields.Text(related="map_id.check", readonly=True)
    original_df = fields.Html(
        readonly=True, help="Minimal transformation from file data and ui settings"
    )
    new_df = fields.Html(readonly=True, help="Transformed dataframe")
    filename = fields.Char()
    file = fields.Binary(related="source_id.file", help="File to process")
    scenari_explained = fields.Text(
        readonly=True, help="Explain transformations consequences"
    )
    source_id = fields.Many2one(
        comodel_name="df.source", help="Original file source record"
    )
    row_viewer = fields.Html(
        readonly=True,
        help="Display first row of dataframe in two columns "
        "to have an idea of the data\n"
        "before import and check if mapping is correct.",
    )

    def create(self, vals):
        """Creation is triggered from df.source, module df_source"""
        wiz = super().create(vals)
        if self.env.context.get("from_field_log"):
            # from field_log model
            # TODO improve this marginal behavior
            return wiz
        res = wiz._process_file()
        if res and hasattr(res, "_name") and res._name == "df.source":
            return {
                "name": _("Updated ..."),
                "res_model": "df.source",
                "view_mode": "form",
                "res_id": res.id,
                "type": "ir.actions.act_window",
                "target": "current",
            }
        return wiz

    def _process_file(self):
        """Full process to wizard preview"""
        self.ensure_one()
        base_df = self._process_df_base()
        if isinstance(base_df, str):
            self.source_id.comment = base_df
            return self.source_id
        elif base_df.is_empty():
            self.source_id.comment = "no data in df: check file"
            return self.source_id
        try:
            df = self._process_resulting_df(base_df=base_df)
        except Exception as e:
            self.source_id.comment = f"{self.source_id.id} - {e.__str__()}"
            return self.source_id
        # display the original dataframe before transformation
        # TODO improve base_df display
        self.original_df = self._2html(base_df)
        # display first row of dataframe in two columns to have an idea of the data
        # before import and check if mapping is correct
        self._display_row(df)
        self._explain_scenari(df)

    def _process_resulting_df(self, base_df=None):
        """Process from file to transformations of the dataframe"""
        if isinstance(base_df, pl.dataframe.frame.DataFrame) and not base_df.is_empty():
            # dataframe has already been build in previous process
            df = base_df
        else:
            df = self._process_df_base()
        # store transformed dataframe
        df = self._apply_transformations(df)
        df = self._build_json_fields(df)
        excluded = self.map_id.field_ids.filtered(lambda s: s.useless).mapped("named")
        with pl.Config(tbl_cols=len(df.columns) - len(excluded)):
            new_df = df
            if excluded:
                # we exclude instead of select to include additional columns
                new_df = df.select(pl.all().exclude(excluded))
            self.new_df = (
                f"{self._2html(self.map_id._remove_cols_from_previewed_df(new_df))}"
            )
        return df

    def _explain_scenari(self, df):
        for rec in self:
            scenari = []
            if rec.map_id.matching_field_id:
                disp = rec.map_id.matching_field_id.display_name
                if rec.map_id.only_update:
                    scenari.append(
                        _(
                            "- only existing records will be updated with "
                            + f"'{rec.map_id.matching_field_id.display_name}'"
                        )
                    )
                    scenari.append(_("- no new record will be created."))
                else:
                    if "id" in df.columns:
                        scenari.append(_("- records will be updated via 'id' column."))
                        scenari.append(_("- no already existing data will be created."))
                    else:
                        scenari.append(_(f"- records will be updated via '{disp}'."))
                        scenari.append(_("- create records if data doesn't exists."))
            rec.scenari_explained = "\n".join(scenari)

    def _process_df_base(self):
        """Produce a dataframe with common transformations for minimal uses
        - rename columns from settings
        - drop useless columns
        """
        return self.map_id._process_df_base(self.source_id)

    def _apply_transformations(self, df):
        """- apply custom transformations, if any
        - fill df_ref column to keep track of data source,
          if model has such field
        """
        self.ensure_one()
        # Custom transformations are defined in _df_alter() method of map_id,
        df = self.map_id._df_alter(df)
        if self._df_ref_in_model():
            # Add df_ref value to keep track of data source
            df = df.with_columns(
                pl.lit(f"df.source,{self.source_id.id}").alias("df_ref")
                # pl.lit(f"{self.source_id.id}").alias("df_ref")
            )
        return df

    def _df_ref_in_model(self):
        """Check if the model destination contains a field named df_ref and built
        like this:

        Field you may add to your model:

            df_ref = fields.Reference(
                string="Source",
                ondelete="set null",
                copy=False,
                selection=[("df.source", "Df Source")],
                help="Keep track of the source of the data, for data imported from file"
            )
        """
        model_name = self.source_id.model.replace(".", "_")
        model = self.env["ir.model.data"].search(
            [("model", "=", "ir.model"), ("name", "=", f"model_{model_name}")], limit=1
        )
        # TODO improve this part
        record = self.env[model.model].browse(model.res_id)
        if record and record.field_id.filtered(lambda s: s.name == "df_ref"):
            return True

    def _build_json_fields(self, df):
        """You may want to regroup in a json field, several columns from the file.
        i.e. use case: you want store to only 1 field, all opening hours of a partner

        To do this, just set mapping field lines config with an existing json field.
        """
        self.ensure_one()
        # Get lines mapped to a json field
        json_lines = self.map_id.field_ids.filtered(
            lambda s: s.field_id.ttype == "json"
        )
        # Create an empty column for each json field in mapping
        # i.e. {'json_field': ['col1', 'colB', 'col5']}
        fields_by_json_fields = {}
        for key, val in {
            x.named: x.field_id.name for x in json_lines.sorted(key="sequence")
        }.items():
            fields_by_json_fields.setdefault(val, []).append(key)
        # fill new columns with related columns dict/json format
        for field_ in fields_by_json_fields:
            col_by_json_field = self.map_id.field_ids.filtered(
                lambda s, field_=field_: s.field_id.name == field_
            ).mapped("named")
            df = df.with_columns(
                pl.struct([pl.col(x) for x in col_by_json_field])
                .alias(field_)
                .struct.json_encode()
            )
            # remove useless columns
            df = df.drop(fields_by_json_fields[field_])
        return df

    def _get_dataframe(self):
        """Compute dataframe from misc spreadsheet sources"""
        return self.map_id._get_dataframe(self.source_id)

    def _process(self):
        """Trigger transformation on dataframe and load in database
        - apply skip to record when required not respected
        """
        df = self._process_resulting_df()

        def count_records(records):
            return records and len(records) or 0

        if self.map_id.flow == "import":
            created_rec, updated_rec = self.env["df.import"]._odoo_df_upsert(
                df, self.map_id.source_id
            )
            if self.source_id:
                count_recs = count_records(created_rec) + count_records(updated_rec)
                if count_recs > 0:
                    # process ends up correctly, we change state to done and set count
                    self.source_id.write({"state": "done", "count": count_recs})
            res = {
                "name": _("Upserted records"),
                "res_model": self.map_id.model_id.model,
                "view_mode": "list,form",
                "type": "ir.actions.act_window",
                "target": "current",  # inline/current
            }
            if self._df_ref_in_model():
                res["domain"] = f"[('df_ref', '=', 'df.source,{self.source_id.id}')]"
            return res

    def _download(self):
        """Download dataframe as file"""
        df = self._process_resulting_df()
        output = io.BytesIO()
        df.write_excel(workbook=output, autofit=True)
        self.file = base64.encodebytes(output.getvalue())
        self.filename = self.filename + ".xlsx"
        return self._reload()

    def _display_row(self, df):
        """Display first row of dataframe in two columns"""
        self.ensure_one()
        if df.is_empty():
            return
        row_dict = df.row(0, named=True)

        def emphase_key(text):
            """"""
            # ^      : début de ligne
            # ([^=]+): capture tout ce qui n'est pas un "=" (la clé)
            # \s* : capture les espaces optionnels avant le "="
            # =      : trouve le signe égal
            pattern = r"^([^=]+)\s*="
            # \1 fait référence au premier groupe capturé (la clé)
            replacement = r"<b>\1</b> ="
            # flags=re.MULTILINE est crucial pour traiter chaque ligne individuellement
            return re.sub(pattern, replacement, text, flags=re.MULTILINE)

        flat = self.env["df.import"]._convert_flat_dict_to_ini(row_dict).strip("\n")
        flat = emphase_key(flat)
        # position of each break line
        idx = [i for i, car in enumerate(flat) if car == "\n"]

        def nl2br(element):
            return element.replace("\n", "<br />")

        s = Template(ROW_TABLE)
        if len(df.columns) == 1:
            self.row_viewer = s.substitute(first=nl2br(flat), second="")
        else:
            self.row_viewer = s.substitute(
                first=nl2br(flat[: idx[round(len(idx) / 2)]]),
                second=nl2br(flat[idx[round(len(idx) / 2)] + 1 :]),
            )

    @staticmethod
    def _2html(df):
        if isinstance(df, pl.dataframe.frame.DataFrame):
            pl.Config.set_tbl_width_chars(200)
            # pylint: disable=W0123 - Eval
            rows = f"Rows count: {df.shape[0]}"
            return f"\n\t\t{rows}<pre>{eval(df.to_init_repr())}\n\t\t</pre>"

    def _reload(self):
        action = self.env.ref(f"{MODULE}.df_file_wiz_action")._get_action_dict()
        action["context"] = safe_eval(action.get("context", "{}"))
        action["res_id"] = self.id
        return action

    def _recompute(self):
        return self.map_id.start()

    def apply(self):
        # Only one public method in this model. Context key exposes other methods
        controller = self.env.context.get("controller")
        return getattr(self, controller, False)()


MODULE = __name__[12 : __name__.index(".", 13)]

ROW_TABLE = """
<div>
    <style>
      .col {
        border: 0px solid #000;
        padding: 25px;
        min-width:1250px;
      }
    </style>
    <table style="width: 90%">
        <tr><td class="col">$first</td><td class="col">$second</td></tr>
    </table>
</div>"""
