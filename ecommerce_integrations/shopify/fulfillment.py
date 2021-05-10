import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
from frappe.utils import cint, cstr, getdate

from ecommerce_integrations.shopify.constants import (
	FULLFILLMENT_ID_FIELD,
	ORDER_ID_FIELD,
	ORDER_NUMBER_FIELD,
	SETTING_DOCTYPE,
)
from ecommerce_integrations.shopify.order import get_sales_order
from ecommerce_integrations.shopify.utils import create_shopify_log


def prepare_delivery_note(order, request_id=None):
	frappe.set_user("Administrator")
	setting = frappe.get_doc(SETTING_DOCTYPE)
	frappe.flags.request_id = request_id

	try:
		sales_order = get_sales_order(cstr(order["id"]))
		if sales_order:
			create_delivery_note(order, setting, sales_order)
		create_shopify_log(status="Success")
	except Exception as e:
		create_shopify_log(status="Error", exception=e, rollback=True)


def create_delivery_note(shopify_order, setting, so):
	if not cint(setting.sync_delivery_note):
		return

	for fulfillment in shopify_order.get("fulfillments"):
		if (
			not frappe.db.get_value(
				"Delivery Note", {FULLFILLMENT_ID_FIELD: fulfillment.get("id")}, "name"
			)
			and so.docstatus == 1
		):

			dn = make_delivery_note(so.name)
			setattr(dn, ORDER_ID_FIELD, fulfillment.get("order_id"))
			setattr(dn, ORDER_NUMBER_FIELD, shopify_order.get("name"))
			setattr(dn, FULLFILLMENT_ID_FIELD, fulfillment.get("id"))
			dn.set_posting_time = 1
			dn.posting_date = getdate(fulfillment.get("created_at"))
			dn.naming_series = setting.delivery_note_series or "DN-Shopify-"
			dn.items = get_fulfillment_items(dn.items, fulfillment.get("line_items"), fulfillment.get("location_id"))
			dn.flags.ignore_mandatory = True
			dn.save()
			dn.submit()
			frappe.db.commit()


def get_fulfillment_items(dn_items, fulfillment_items, location_id=None):
	# local import to avoid circular imports
	from ecommerce_integrations.shopify.product import get_item_code

	warehouse = _get_warehouse_map(location_id)

	return [
		dn_item.update({"qty": item.get("quantity"), "warehouse": warehouse})
		for item in fulfillment_items
		for dn_item in dn_items
		if get_item_code(item) == dn_item.item_code
	]


def _get_warehouse_map(shopify_location_id: str) -> str:
	shopify_location_id = str(shopify_location_id)
	setting = frappe.get_cached_doc(SETTING_DOCTYPE)

	if setting.shopify_warehouse_mapping and shopify_location_id:
		for wh in setting.shopify_warehouse_mapping:
			if wh.shopify_location_id == shopify_location_id:
				return wh.erpnext_warehouse

	# return default WH
	return setting.warehouse
