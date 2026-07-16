# Specification: Enhance product inventory tracking

## Objective
Improve the inventory tracking capabilities of the Bill Express application to provide better visibility and control over stock levels.

## Background
Currently, the application allows creating products and generating invoices, which automatically deducts stock. However, a more robust inventory management system is needed for a seamless retail experience.

## Requirements
- Introduce stock history or transaction logging for products.
- Provide low stock alerts on the dashboard based on a configurable threshold.
- Allow manual stock adjustments with reason codes (e.g., restock, damage, audit).

## Technical Approach
- Add a new `inventory_transactions` table to the SQLite database.
- Create API endpoints in Express to record and fetch stock transactions.
- Update the frontend React components to display stock history and allow manual adjustments.