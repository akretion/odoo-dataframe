{
    "name": "Df (dataframe) Source",
    "version": "18.0.1.0.0",
    "summary": "Base module for file or database sources for DataFrame",
    "category": "Data",
    "license": "LGPL-3",
    "author": "Akretion",
    "development_status": "Beta",
    "website": "https://github.com/akretion/odoo-dataframe",
    "maintainers": ["bealdav"],
    "depends": [
        "mail",
        "record_field_log",
    ],
    "external_dependencies": {
        "python": [
            "polars",
        ]
    },
    "data": [
        "security/group.xml",
        "security/ir.model.access.xml",
        "data/action.xml",
        "views/df_source.xml",
        "views/matching_field.xml",
        "views/menu.xml",
    ],
    "installable": True,
}
