# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn


@frappe.whitelist()
def get_top_level_groups(root_group=None, warehouse=None, company=None):
	if not root_group:
		root_group = "All Item Groups"

	IG = frappe.qb.DocType("Item Group")
	children = (
		frappe.qb.from_(IG)
		.select(IG.name, IG.lft, IG.rgt)
		.where(IG.parent_item_group == root_group)
		.orderby(IG.lft)
	).run(as_dict=True)

	result = []
	for child in children:
		agg = _aggregate_for_group(child.lft, child.rgt, warehouse, company)
		qty = flt(agg.get("qty") or 0, 2)
		value = flt(agg.get("value") or 0, 2)
		result.append({
			"item_group": child.name,
			"qty": qty,
			"valuation_rate": flt(value / qty, 2) if qty else 0,
			"value": value,
			"is_group": 1,
		})
	return result


def _aggregate_for_group(lft, rgt, warehouse=None, company=None):
	IG = frappe.qb.DocType("Item Group")
	Item = frappe.qb.DocType("Item")
	Bin = frappe.qb.DocType("Bin")
	Wh = frappe.qb.DocType("Warehouse")

	q = (
		frappe.qb.from_(Bin)
		.join(Item).on(Item.name == Bin.item_code)
		.join(IG).on(IG.name == Item.item_group)
		.join(Wh).on(Wh.name == Bin.warehouse)
		.select(
			fn.Sum(Bin.actual_qty).as_("qty"),
			fn.Sum(Bin.stock_value).as_("value"),
		)
		.where(IG.lft >= lft)
		.where(IG.rgt <= rgt)
	)

	if company:
		q = q.where(Wh.company == company)
	if warehouse:
		q = q.where(Bin.warehouse == warehouse)

	result = q.run(as_dict=True)
	return result[0] if result else {}


@frappe.whitelist()
def get_group_children(item_group, warehouse=None, company=None):
	IG = frappe.qb.DocType("Item Group")
	child_groups = (
		frappe.qb.from_(IG)
		.select(IG.name, IG.lft, IG.rgt)
		.where(IG.parent_item_group == item_group)
		.orderby(IG.lft)
	).run(as_dict=True)

	if child_groups:
		result = []
		for child in child_groups:
			agg = _aggregate_for_group(child.lft, child.rgt, warehouse, company)
			qty = flt(agg.get("qty") or 0, 2)
			value = flt(agg.get("value") or 0, 2)
			result.append({
				"item_group": child.name,
				"qty": qty,
				"valuation_rate": flt(value / qty, 2) if qty else 0,
				"value": value,
				"is_group": 1,
			})
		return result

	# Leaf group — return individual items
	Item = frappe.qb.DocType("Item")
	Bin = frappe.qb.DocType("Bin")
	Wh = frappe.qb.DocType("Warehouse")

	q = (
		frappe.qb.from_(Bin)
		.join(Item).on(Item.name == Bin.item_code)
		.join(Wh).on(Wh.name == Bin.warehouse)
		.select(
			Item.item_code,
			Item.item_name,
			fn.Sum(Bin.actual_qty).as_("qty"),
			fn.Sum(Bin.stock_value).as_("value"),
		)
		.where(Item.item_group == item_group)
		.groupby(Item.item_code, Item.item_name)
		.orderby(Item.item_code)
	)

	if company:
		q = q.where(Wh.company == company)
	if warehouse:
		q = q.where(Bin.warehouse == warehouse)

	items = q.run(as_dict=True)
	result = []
	for item in items:
		qty = flt(item.get("qty") or 0, 2)
		value = flt(item.get("value") or 0, 2)
		result.append({
			"item_code": item["item_code"],
			"item_name": item["item_name"],
			"qty": qty,
			"valuation_rate": flt(value / qty, 2) if qty else 0,
			"value": value,
			"is_group": 0,
		})
	return result
