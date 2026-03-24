import base64
import csv
import inspect
import io
import logging
import os

import polars as pl

from odoo import Command as cmd
from odoo import _, exceptions, fields, models
from odoo.tools.safe_eval import safe_eval

logger = logging.getLogger(__name__)


class DataMap(models.Model):
    _name = "data.map"
    _inherit = "mail.thread"
    _description = "File Configuration"
    _rec_name = "code"
    _rec_names_search = ["model_id", "code"]

    model_id = fields.Many2one(
        comodel_name="ir.model",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    code = fields.Char(
        required=True, help="Allow to browse between several identical models"
    )
    source_id = fields.Many2one(comodel_name="df.source", readonly=True, copy=False)
    pattern_file = fields.Binary(
        inverse="_inverse_file_template", copy=False, help="Template file to download"
    )
    pattern_file_name = fields.Char()
    file_type = fields.Selection([("csv", "csv"), ("ods", "ods"), ("xlsx", "xlsx")])
    comma_as_decimal = fields.Boolean(
        help="In csv case, if decimal is defined by a ',' instead of '.'"
    )
    parse_date = fields.Boolean(help="In csv case, try to guess date string format")
    comment = fields.Text(help="Explaining notes for wizard")
    check = fields.Text(readonly=True, help="Primary checks on datafame before process")
    flow = fields.Selection(
        selection=[("import", "Import")],
        default="import",
        tracking=True,
        help="Some other behaviors can be implemented",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("configured", "Configured"),
            ("closed", "Closed"),
        ],
        default="draft",
        copy=False,
        tracking=True,
    )
    field_ids = fields.One2many(
        comodel_name="field.map", inverse_name="map_id", copy=False
    )
    expression = fields.Text(
        compute="_compute_df_string_expression",
        store=False,
        help="Additional column to dataframe with formulae\n"
        "Use polars with_columns de polars \n i.e. "
        "'df = df.with_columns([polars expression]))",
    )
    multi_value_id = fields.Many2one(
        comodel_name="ir.model.fields",
        copy=False,
        inverse="_inverse_multi_value",
        help="Json field to store multi data in one field: populate field in rules",
    )
    config = fields.Text(inverse="_inverse_check_config")
    readonly = fields.Boolean()
    sequence = fields.Integer()
    transformation = fields.Selection(
        selection=[],
        tracking=True,
        help="Apply processing scenari (defined in your code) to apply "
        + "to the dataframe ",
    )
    on_fail = fields.Selection(
        selection=[("stop", "Stop"), ("skip", "Skip records")],
        default="stop",
        tracking=True,
        help="What should be the behavior in case of failure on validation\n"
        " - Stop: stop the process by raising an exception\n"
        " - Skip records: current line'll be ignored from the next process",
    )
    matching_field_id = fields.Many2one(
        comodel_name="matching.field",
        string="Matching keys",
        help="Field used to update record if match",
    )
    only_update = fields.Boolean(
        help="Only update existing records, do not create new ones"
    )
    freeze_field_rules = fields.Boolean(
        help="Freeze field rules to prevent update when new inserted file"
    )

    def _inverse_check_config(self):
        for rec in self:
            if rec.config:
                try:
                    safe_eval(rec.config)
                except Exception as err:
                    raise exceptions.ValidationError(
                        _(f"Invalid format\n{rec.config}\n{err}")
                    ) from err

    def _inverse_file_template(self):
        for rec in self:
            if rec.pattern_file and not rec.freeze_field_rules:
                columns = rec._extract_columns_from_template_file()
                rec.fill_field_rules(columns)
            self._upsert_df_source()

    def _upsert_df_source(self):
        self.ensure_one()
        source_vals = {
            "file": self.pattern_file,
            "name": self.pattern_file_name,
            "map_id": self.id,
            "model": self.model_id.model,
        }
        if self.source_id and self.source_id.state == "draft":
            self.source_id.write(source_vals)
        else:
            source_vals["name"] = f"{self.pattern_file_name}"
            self.source_id = self.env["df.source"].create(source_vals).id

    def _compute_df_string_expression(self):
        """Display expressions"""
        for rec in self:
            code_sources = get_transformation_source_code(
                self, "_df_alter", self.transformation
            )
            code_sources.extend(
                get_transformation_source_code(
                    self, "_df_pre_alter", self.transformation
                )
            )
            express = []
            for code in code_sources:
                # We remove indentation
                express.append(code.replace("\n    ", "\n")[4:])
            rec.expression = "\n".join(express)

    def _df_alter(self, df):
        """Call an hypothetic transformation method"""
        return self._get_transformed_df("_df_alter", df)

    def _df_pre_alter(self, df):
        """Call an hypothetic pre transformation method"""
        return self._get_transformed_df("_df_pre_alter", df)

    def _get_transformed_df(self, prefix_method, df):
        """Call conventionaly named method to transform dataframe, if exist"""
        res = getattr(self, f"{prefix_method}_{self.transformation}", None)
        if res:
            return res(df)
        return df

    def _df_validate(self, df):
        """Call an hypothetic validation method"""
        res = getattr(self, f"_df_validate_{self.transformation}", None)
        if res:
            res = res(df)
        if isinstance(res, list):
            if not res:
                # we must reset field
                self.check = False
            else:
                self.check = "\n".join(res)

    def _extract_columns_from_template_file(self):
        self.ensure_one()
        # TODO: implement mimetype
        columns = False
        logger.info("Extract columns from file %s", self.pattern_file_name)
        if self.pattern_file_name.endswith(".csv"):
            line = (
                io.BytesIO(base64.b64decode(self.pattern_file))
                .readline()
                .decode("utf-8")
            )
            dialect = csv.Sniffer().sniff(line)
            columns = line.replace(dialect.lineterminator, "").split(dialect.delimiter)
            self.file_type = "csv"
        elif self.pattern_file_name.endswith(".xlsx"):
            df = pl.read_excel(
                source=io.BytesIO(base64.b64decode(self.pattern_file)),
            )
            columns = df.columns
            self.file_type = "xlsx"
        elif self.pattern_file_name.endswith(".ods"):
            df = pl.read_ods(
                source=io.BytesIO(base64.b64decode(self.pattern_file)),
            )
            columns = df.columns
            self.file_type = "ods"
        return columns

    def fill_field_rules(self, columns=None):
        logger.info("  Fill field rules ")
        columns = columns or self.field_ids.mapped("name")
        config = self.config and safe_eval(self.config) or {}
        all_fields = self.env["ir.model.fields"].search(
            [("model", "=", self.model_id.model)]
        )
        # i.e. {'actif': 256, 'ville': 265} for res.partner in lower
        field_strings_id_mapping = {x.field_description.lower(): x for x in all_fields}
        # i.e. {'active': 256, 'city': 265} for res.partner
        field_names_id_mapping = {x.name: x for x in all_fields}
        rules = []

        def config_by_key(key, col):
            return (
                config
                and config.get(key)
                and config[key]
                and config[key].get(col)
                or False
            )

        for col in columns:
            # col is raw string from file
            renamed = ""
            conf_renamed = config_by_key("renamed", col)
            # We compare in lower case String
            field_ = field_strings_id_mapping.get(conf_renamed or col.lower())
            if field_:
                renamed = field_.name
            # We compare in lower case field Name with conf_renamed
            field_ = field_ or field_names_id_mapping.get(conf_renamed or col.lower())
            if field_:
                renamed = field_.name
            renamed = renamed or conf_renamed
            dico = {
                "name": col,
                "renamed": renamed,
                "multi": config_by_key("multi", renamed or col),
                "sequence": config_by_key("sequence", renamed or col),
                "useless": config_by_key("useless", renamed or col),
                "field_id": field_ and field_.id or False,
            }
            rules.append(cmd.create(dico))
        if rules:
            self.field_ids = [cmd.clear()] + rules

    def _inverse_multi_value(self):
        for rec in self:
            if rec.multi_value_id:
                # initialize the multi field
                rec.field_ids = [
                    cmd.update(x.id, {"multi": True})
                    for x in rec.field_ids
                    if x.field_id.ttype == "json"
                ]
                # populate json field with multi values
                rec.field_ids = [
                    cmd.update(x.id, {"field_id": rec.multi_value_id.id})
                    for x in rec.field_ids
                    if x.multi
                ]

    def start(self):
        self.ensure_one()
        if self.source_id.state != "draft":
            self._upsert_df_source()
        # TODO check named are single
        return self.source_id.start()

    def reset(self):
        self.ensure_one()
        self.state = "draft"

    def validate(self):
        self.ensure_one()
        self.state = "configured"

    def close(self):
        self.ensure_one()
        self.state = "closed"

    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {})
        default["code"] = f"{self.code} (copy)"
        return super().copy(default)

    def serialize_config(self):
        def get_dict_format(column):
            def key(y, column):
                """Return renamed except when column is renamed to keep
                original name as key of dict"""
                return y.name if column == "renamed" else y.named

            def value(y, column):
                "Prevent to add quote to boolean values"
                return (
                    y[column]
                    if isinstance(y[column], bool)
                    else '"' + str(y[column]) + '"'
                )

            res = [
                '"' + f"{key(x, column)}" + '": ' + f"{value(x, column)}"
                for x in self.field_ids
                if x[column]
            ]
            res = ", ".join(
                [x for x in res if x[: x.index(":")] != x[x.index(": ") + 2 :]]
            )
            if res:
                res = "{" + res + "}"
                try:
                    res = safe_eval(res)
                except Exception as err:  # pragma: no cover
                    # because data comes from regular UI, we can't test fail case
                    # but we want to prevent it to break
                    # the system without clear message
                    raise exceptions.ValidationError(
                        _(f"Invalid format col: {column}\n{res}\n{err}")
                    ) from err
                return res
            return

        mdict = {}
        # skipped fields'll have an upper sequence
        for elm in self.field_ids:
            if elm.useless:
                elm.sequence = elm.sequence + 500
        for mvar in ("renamed", "useless", "multi", "sequence"):
            sub_dict = get_dict_format(mvar)
            if sub_dict:
                mdict[mvar] = sub_dict
        self.config = f"{mdict}".replace("}, '", "},\n'")

    def _get_dataframe(self, source=None):
        """Compute dataframe from misc spreadsheet sources"""
        source = source or self.source_id
        try:
            if self.file_type == "xlsx":
                df = pl.read_excel(source=base64.b64decode(source.file))
            elif self.file_type == "ods":
                df = pl.read_ods(source=base64.b64decode(source.file))
            else:
                file = base64.b64decode(source.file)
                line = io.BytesIO(file).readline().decode("utf-8")
                dialect = csv.Sniffer().sniff(line)
                decimal = self.comma_as_decimal
                parse_date = self.parse_date
                df = pl.read_csv(
                    source=file,
                    separator=dialect.delimiter,
                    decimal_comma=decimal,
                    try_parse_dates=parse_date,
                )
                # some file because of windows line terminator lead to blank line
                # after each line, we need to remove them
                # TODO probably a better way to proceed than loading them
                # and filtering them
                is_empty_or_null = pl.all().is_null() | (pl.all().cast(pl.String) == "")
                df = df.filter(~pl.all_horizontal(is_empty_or_null))
        except Exception as err:
            error = err
            raise exceptions.ValidationError(error) from err
        return df.with_row_index(name="N°", offset=1)

    def _process_df_base(self, source=None):
        """Produce a dataframe with common transformations for minimal uses
        - rename columns from settings
        - drop useless columns
        """
        source = source or self.source_id
        df = self._get_dataframe(source)
        # rename columns
        df = df.rename({x.name: x.named for x in self.field_ids})
        # remove useless columns
        df = df.drop([x.named for x in self.field_ids if x.useless])
        # first steps of transformation
        df = self._df_pre_alter(df)
        self._df_validate(df)
        return df

    def _check_missing_cols(self, df, cols):
        missing = [x for x in cols if x not in df.columns]
        if missing:
            raise exceptions.UserError(f"Missing columns {missing} field rules")

    def _remove_cols_from_previewed_df(self, df):
        """This method is used to remove columns from dataframe preview
        but still used for transformation and import."""
        return df

    def _add_base_data(self, name):
        """Add data for tests or demo"""
        if not self.search([("code", "=", name)]):
            demo = self.create(
                {
                    "model_id": self.env.ref("base.model_res_partner").id,
                    "code": name,
                    "pattern_file_name": f"{name}_file.csv",
                }
            )
            return demo

    def _add_demo_data(self, name):
        "Triggered from demo xml file"
        demo = self._add_base_data(name or "hello")
        if not demo:
            return
        self.env["ir.model.data"].create(
            {
                "res_id": demo.id,
                "model": demo._name,
                "module": "__",
                "name": f"{name}_data_map",
                "noupdate": False,
            }
        )

        demo.pattern_file = base64.b64encode(
            b"Country;name;Town;Street;color\n"
            + b"France;Akretion;Lyon;rue de l'arbre sec;green\n"
            + b"Belgium;Achimanapse;Brussels;rue de ...;purple\n"
            + b"United Kingdom;Larry_the_cat;London;10 downing street;mauve\n"
        )
        return demo


def get_transformation_source_code(record, method_name, condition):
    """Capture code from _alter_df_{condition}() method and chidren methods
    to document transformation"""
    funcs, results = [], []
    installed_modules = record.env["ir.module.module"].search(
        [("state", "=", "installed")]
    )
    # we need to add current module to this list because odoo unit tests are running
    # seems to remove this state for being tested module
    # that's not the case for pytest
    current_module = __name__[12 : __name__.index(".", 13)]
    installed_module_names = set(installed_modules.mapped("name") + [current_module])

    def file_path_in_installed_module(file_path):
        parts = file_path.split(os.sep)
        return next((p for p in reversed(parts) if p in installed_module_names), None)

    def get_func_source_code(func):
        raw_func = getattr(func, "__func__", func)
        file_path = inspect.getsourcefile(raw_func)
        if file_path_in_installed_module(file_path):
            full_source = inspect.getsource(raw_func)
            if full_source:
                return full_source

    # Pour éviter de traiter la même implémentation plusieurs fois
    for cls in type(record)._BaseModel__base_classes:
        func = getattr(cls, f"{method_name}_{condition}", None)
        if func:
            funcs.append(func)
            funcs.extend(find_children_methods(cls, method_name, condition))
        for func_ in funcs:
            res = get_func_source_code(func_)
            if res:
                results.append(res)
        # TODO prevent duplicates block code
        results = list(set(results))
    return results


def find_children_methods(cls_or_obj, prefix, condition):
    original_method = f"{prefix}_{condition}"
    # filter methods begining with prefix
    # and containing condition anywhere after
    # but different from the original_method
    matches = [
        m
        for m in dir(cls_or_obj)
        if m.startswith(prefix) and condition in m and m != original_method
    ]
    results = []
    for method_name in matches:
        func = getattr(cls_or_obj, method_name)
        # Ensure that's a real function/method
        if inspect.isroutine(func):
            results.append(func)
    return results
