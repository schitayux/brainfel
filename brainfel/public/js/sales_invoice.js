frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        // Eliminar versiones previas del botón para evitar duplicados
        frm.remove_custom_button(__('Certifica FEL'));
        frm.remove_custom_button('Certifica FEL');

        console.log("FEL Button Check:", {
            name: frm.doc.name,
            docstatus: frm.doc.docstatus,
            bfel_uuid: frm.doc.bfel_uuid,
            is_new: frm.doc.__islocal
        });

        // El botón solo debe aparecer en documentos SUBMITTED y que no tengan UUID
        if (frm.doc.docstatus === 1 && !frm.doc.bfel_uuid) {
            frm.add_custom_button(__('Certifica FEL'), function() {
                let prefix = frm.doc.name.substring(0, 4);
                
                let certify_action = function(motivo_ajuste) {
                    frappe.call({
                        method: 'brainfel.api.certify_sales_invoice.certify_sales_invoice',
                        args: {
                            sales_invoice_name: frm.doc.name,
                            motivo_ajuste: motivo_ajuste
                        },
                        freeze: true,
                        freeze_message: __('Certificando documento FEL...'),
                        callback: function(r) {
                            if (!r.exc && r.message && r.message.success) {
                                frappe.msgprint({
                                    title: __('Éxito'),
                                    indicator: 'green',
                                    message: __('Documento certificado correctamente.')
                                });
                                frm.reload_doc();
                            }
                        }
                    });
                };

                if (prefix === "NCRE" || prefix === "NDEB") {
                    frappe.prompt({
                        label: 'Motivo de Ajuste (Nota)',
                        fieldname: 'motivo_ajuste',
                        fieldtype: 'Data',
                        reqd: 1
                    }, function(values) {
                        certify_action(values.motivo_ajuste);
                    }, 'Certificación FEL', 'Certificar');
                } else {
                    certify_action();
                }
            });
            
            // Poner el botón como primario (Azul)
            frm.change_custom_button_type(__('Certifica FEL'), null, 'primary');
        }
    },
    before_cancel: function(frm) {
        if (frm.doc.bfel_status === '02 Procesada' && frm.doc.bfel_uuid && !frm.doc.__fel_cancelled) {
            frappe.validated = false; // Detener la anulación estándar temporalmente
            
            frappe.prompt({
                label: 'Motivo de anulación FEL',
                fieldname: 'motivo_anulacion',
                fieldtype: 'Data',
                reqd: 1
            }, function(values) {
                frappe.call({
                    method: 'brainfel.api.certify_sales_invoice.cancel_sales_invoice_fel',
                    args: {
                        sales_invoice_name: frm.doc.name,
                        motivo_anulacion: values.motivo_anulacion
                    },
                    freeze: true,
                    freeze_message: __('Anulando en portal FEL...'),
                    callback: function(r) {
                        if (!r.exc && r.message && r.message.success) {
                            frappe.msgprint({
                                title: __('Éxito'),
                                indicator: 'green',
                                message: r.message.message || __('Documento anulado correctamente en FEL.')
                            });
                            
                            // Marcar como anulado localmente para que este mismo trigger lo deje pasar la próxima vez
                            frm.doc.__fel_cancelled = true;
                            
                            // Ejecutar la anulación real en ERPNext
                            frm.save('cancel');
                        }
                    }
                });
            }, 'Anulación FEL', 'Anular');
        }
    }
});
