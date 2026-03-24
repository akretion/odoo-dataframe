{
    "name": "DF File Process",
    "version": "18.0.2.0.0",
    "summary": "Allow to create a Polars dataframe from file and "
    "process it according to rules.",
    "category": "Reporting",
    "license": "LGPL-3",
    "author": "Akretion",
    "development_status": "Beta",
    "website": "https://github.com/akretion/odoo-dataframe",
    "maintainers": ["bealdav"],
    "depends": [
        "df_process",
    ],
    "external_dependencies": {
        "python": [
            "fastexcel",
            "odoo-test-helper>2.1.2",
            "xlsxwriter>3.2.8",
            "pointblank[pl]",
        ]
    },
    "data": [
        "views/data_map.xml",
        "views/df_field.xml",
        "views/df_source.xml",
        "wizards/df_file_wiz.xml",
        "security/ir.model.access.xml",
    ],
    "demo": [
        "data/demo.xml",
    ],
    "installable": True,
}  # pragma: no cover
