from odoo.upgrade import util

def migrate(cr, version):
    if not version:
        return

    # 1. LISTA DE MÓDULOS A DESINSTALAR (Basado en tu lista)
    # Esto evita el error "Some modules are not loaded" al borrar las carpetas físicas.
#    modules_to_clean = [
#        'account_financial_amount', 'account_financial_report', 'date_range',
#        'exe_account_custom_report', 'exe_account_remito', 'exe_add_button_purchase',
#        'exe_crm_custom', 'exe_fleet_vehicle', 'exe_import_folder_custom',
#        'exe_mrp_custom', 'exe_preprinted_report', 'exe_product_template_fields',
#        'exe_purchase_requisition_custom', 'exe_stock_picking_custom',
#        'l10n_ar_bank', 'l10n_ar_withholding', 'om_account_accountant',
#        'om_account_asset', 'om_account_budget', 'product_ux', 'report_xlsx'
#    ]

    modules_to_clean = [
        # Los que vas a borrar físicamente ahora:
        'account_financial_amount', 'account_financial_report', 'date_range',
        'exe_account_custom_report', 'exe_account_remito', 'exe_add_button_purchase',
        'exe_crm_custom', 'exe_fleet_vehicle', 'exe_import_folder_custom',
        'exe_mrp_custom', 'exe_preprinted_report', 'exe_product_template_fields',
        'exe_purchase_requisition_custom', 'exe_stock_picking_custom',
        'l10n_ar_bank', 'l10n_ar_withholding', 'om_account_accountant',
        'om_account_asset', 'om_account_budget', 'product_ux', 'report_xlsx',

        # Los que Odoo reclamaba en el log anterior (complementarios):
        'account_check', 'account_move_custom_rate', 'account_payment_fix', 
        'account_payment_group', 'accounting_pdf_reports', 'date_range_account', 
        'exchange_rate', 'exe_add_state_draft_check', 'import_folder_new', 
        'l10n_ar_account_inflation_adjust', 'l10n_ar_partner', 
        'l10n_ar_report_withholdings_suffered', 'test_crm_fields',
        'sale_purchase_previous_product_cost', 'stock_last_purchase_price'
    ]

    # Marcamos los módulos como desinstalados en la DB
    cr.execute("""
        UPDATE ir_module_module 
        SET state = 'uninstalled' 
        WHERE name IN %s AND state != 'uninstalled'
    """, (tuple(modules_to_clean),))

    # 2. ELIMINACIÓN DE VISTAS CRÍTICAS (l10n_ar_withholding)
    # Para evitar errores de herencia XML al intentar cargar el registro
    views_to_remove = [
        "l10n_ar_withholding.withholdings_report_general",
        "l10n_ar_withholding.view_withholdings_report_form",
        "l10n_ar_withholding.report_payment_withholding",
        "l10n_ar_withholding.report_payment_withholding_document",
        "l10n_ar_withholding.view_account_move_perceptions_form",
        "l10n_ar_withholding.view_account_export_sicore",
        "l10n_ar_withholding.view_account_export_sicore_form",
        "l10n_ar_withholding.view_partner_property_form",
        "l10n_ar_withholding.view_account_payment_group_form",
    ]

    for view_xmlid in views_to_remove:
        util.remove_view(cr, view_xmlid)

    # 3. ELIMINACIÓN DE CAMPOS DE RES.USERS (Provocaban el CRITICAL)
    fields_to_remove = [
        ('res.users', 'empleador_padron'),
        ('res.users', 'actividad_monotributo_padron'),
        ('res.users', 'monotributo_padron'),
        ('res.users', 'integrante_soc_padron'),
        ('res.users', 'imp_iva_padron'),
        ('res.users', 'imp_ganancias_padron'),
        ('res.users', 'estado_padron'),
        ('res.users', 'afip_responsability_type_id'),
        ('res.users', 'start_date'),
        ('res.users', 'gross_income_jurisdiction_ids'),
        ('res.users', 'gross_income_type'),
        ('res.users', 'gross_income_number'),
        ('res.users', 'default_regimen_ganancias_id'),
        ('res.users', 'drei'),
        ('res.users', 'iibb_number'),
    ]

    for model, field in fields_to_remove:
        util.remove_field(cr, model, field)

    # 4. LIMPIEZA DE TABLAS TRANSITORIAS REBELDES
    # Eliminamos las tablas físicas para que el upgrade no intente procesar sus campos
    transient_tables = [
        'ar_withholdings_reports',
        'account_export_sicore'
    ]
    
    for table in transient_tables:
        cr.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

    # Limpiamos referencias de campos huérfanos en modelos transient
    util.remove_field(cr, 'account.export.sicore', 'write_date')
    util.remove_field(cr, 'ar.withholdings.reports', 'date_to')
    util.remove_field(cr, 'ar.withholdings.reports', 'date_from')
