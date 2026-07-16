# 🧾 Bill Express

<div align="center">
  <img src="public/logo.png" alt="Bill Express Logo" width="120"/>
</div>

<p align="center">
  <strong>A modern, full-stack Point of Sale (POS) and billing application designed for seamless retail management.</strong>
</p>

<p align="center">
  <a href="https://github.com/dhaatrik/bill-express/actions/workflows/ci.yml">
    <img src="https://github.com/dhaatrik/bill-express/actions/workflows/ci.yml/badge.svg" alt="CI Status" />
  </a>
  <a href="https://img.shields.io/badge/license-MIT-blue.svg">
    <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" />
  </a>
  <a href="https://img.shields.io/badge/react-19.0.0-blue.svg">
    <img src="https://img.shields.io/badge/react-19.0.0-blue.svg" alt="React: 19.0.0" />
  </a>
  <a href="https://img.shields.io/badge/typescript-5.8.2-blue.svg">
    <img src="https://img.shields.io/badge/typescript-5.8.2-blue.svg" alt="TypeScript: 5.8.2" />
  </a>
  <a href="https://img.shields.io/badge/vite-6.2.0-brightgreen.svg">
    <img src="https://img.shields.io/badge/vite-6.2.0-brightgreen.svg" alt="Vite: 6.2.0" />
  </a>
</p>

---

## 📖 Overview

**Bill Express** simplifies daily retail operations by offering an all-in-one suite for managing customers, tracking product inventory, and generating professional invoices. We built Bill Express to solve the complexity of traditional billing systems—many of which lack intuitive interfaces, modern web architectures, and seamless GST/tax integrations.

By leveraging React 19 and Vite for a lightning-fast frontend, and Express.js coupled with a robust SQLite database for the backend, Bill Express provides a highly responsive, easily deployable local Point of Sale solution for modern retail environments.

## 📑 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Technologies Used](#-technologies-used)
- [Installation & Requirements](#-installation--requirements)
- [Usage Instructions & Examples](#-usage-instructions--examples)
- [Testing](#-testing)
- [Contributing](#-contributing)
- [License](#-license)

## ✨ Key Features

- **📊 Dashboard Analytics**: Gain real-time insights into gross sales, track top-performing products, and monitor low-stock items at a glance.
- **📦 Product Management**: Create, update, and comprehensively manage inventory. Includes built-in support for HSN codes, custom GST rates, and dynamic stock tracking.
- **👥 Customer Directory**: Maintain a robust database of your clients, complete with GSTIN tracking and lifetime-value metrics.
- **💳 Advanced Invoice Generation**: Swiftly generate B2B and B2C invoices. Supports automatic subtotal calculation, automated tax splitting (SGST/CGST/IGST), discount handling, and payment tracking. Canceled invoices automatically restore product stock.

## 🛠 Technologies Used

The project is built on a modern, robust tech stack:

### Frontend
- **React 19**: Leverages the latest React paradigms for a highly interactive UI.
- **Vite 6**: Provides lightning-fast HMR and optimized production builds.
- **Tailwind CSS (v4)**: For rapid, highly-customizable atomic styling.
- **Framer Motion & Recharts**: Delivering smooth animations and interactive data visualizations.
- **Lucide React**: Clean and beautiful minimal icons.

### Backend
- **Express.js (Node.js)**: A lightweight, fast web framework handling all API routes.
- **SQLite3 (`better-sqlite3`)**: An incredibly fast, zero-configuration local database that's perfect for localized POS deployments.
- **TypeScript**: End-to-end type safety for rock-solid reliability.

## 🚀 Installation & Requirements

### System Requirements
- [Node.js](https://nodejs.org/) (v20 or higher recommended)
- npm (v9 or higher recommended)

### Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dhaatrik/bill-express.git
   cd bill-express
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start the Development Server:**
   ```bash
   npm run dev
   ```
   *The backend Express server and the Vite frontend will spin up concurrently. You can access the application at `http://localhost:3000`.*

4. **Build for Production (Optional):**
   ```bash
   npm run build
   ```

> [!WARNING]
> **Security Notice**: This repository comes with a `testingcredentials` file intended to easily bypass authentication during local evaluation or testing. **You MUST delete `testingcredentials`** before deploying Bill Express to any production environment to prevent unauthorized access! Configure the `ADMIN_USERNAME` and `ADMIN_PASSWORD` environments securely instead.

## 💻 Usage Instructions & Examples

### 1. Web Application Workflow
1. Navigate to `http://localhost:3000` in your browser.
2. Log in with your administration credentials to access the Dashboard.
3. To generate a bill:
   - Navigate to the **"New Bill"** tab.
   - Select a customer from your directory (or create a new one).
   - Add items via the product search. 
   - Apply any necessary percentage or flat discounts. Bill Express will auto-calculate taxes (CGST/SGST/IGST).
   - Print or save the invoice securely!

### 2. Interacting with the API Programmatically

If you are expanding the ecosystem, you can utilize the RESTful APIs directly:

**Creating a New Product:**
```bash
curl -X POST http://localhost:3000/api/products \
  -H "Content-Type: application/json" \
  -d '{
        "code": "P001", 
        "name": "Wireless Mouse", 
        "category": "Electronics", 
        "unit": "pcs", 
        "price_ex_gst": 500, 
        "gst_rate": 18, 
        "hsn_code": "8471", 
        "stock": 50
      }'
```

**Fetching Dashboard Analytics:**
```bash
curl http://localhost:3000/api/dashboard/analytics
```

## 🧪 Testing

Bill Express ensures high stability and prevents regressions using a comprehensive automated test suite powered by **Vitest** and **React Testing Library**.

To run the entire integration and unit test suite:

```bash
npm run test
```

For static analysis and type checking:

```bash
npm run lint
```

## 🤝 Contributing

We heartily welcome contributions from the community to improve Bill Express! Whether it's a bug fix, new feature, or documentation update, your help is appreciated.

Please read through our [Contribution Guidelines](CONTRIBUTING.md) to understand the process for submitting issues, feature requests, and Pull Requests to this repository.

## 📜 License

This project is open-source and released under the [MIT License](LICENSE). You are free to utilize, modify, and distribute this software in compliance with the license constraints.
