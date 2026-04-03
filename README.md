### Cecypo Reports

Custom reports pack for ERPNext, providing enhanced financial and inventory history reports.

### Reports

| Report | Module | Description |
|--------|--------|-------------|
| Sales Report Enhanced | Accounts | Sales invoices with payment mode breakdown |
| Accounts Receivable Summary Enhanced | Accounts | AR summary with ageing and payment details |
| Day Book | Accounts | GL entries by date — detailed or summarised by voucher type |
| Item History | Stock | Purchase and sales history for a specific item |
| Customer History | Accounts / Sales | Item-wise sales summary per customer with drill-down |
| Supplier History | Accounts / Purchase | Item-wise purchase summary per supplier with drill-down |

### Pages

| Page | URL | Description |
|------|-----|-------------|
| Transaction History | /transaction-history | Tabbed view: Item History, Customer History, Supplier History with side-by-side tables and accordion drill-down |

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app cecypo_frappe_reports
bench --site <site-name> migrate
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/cecypo_frappe_reports
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

agpl-3.0
