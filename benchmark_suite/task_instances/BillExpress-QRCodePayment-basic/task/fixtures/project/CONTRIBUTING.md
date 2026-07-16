# Contributing to Bill Express

First off, thanks for taking the time to contribute! Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

## Getting Started

1. **Fork the repository** to your own GitHub account.
2. **Clone the project** to your local machine:
   ```bash
   git clone https://github.com/dhaatrik/bill-express
   cd bill-express
   ```
3. **Install dependencies**:
   ```bash
   npm install
   ```

## Development Workflow

1. Create a branch for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your code changes.
3. Keep your commits atomic, and use descriptive commit messages.
4. Ensure the test suite passes locally to avoid CI failures:
   ```bash
   npm run test
   ```
5. Check for types and linting errors:
   ```bash
   npm run lint
   ```

## Submitting Pull Requests

- When you are ready to submit your PR, open a PR from your branch against the `main` branch.
- Describe the changes you have made and the rationale behind them.
- Reference any relevant issues in the PR description (e.g., "Closes #1").

## Code of Conduct

Please note that this project is released with a Contributor Code of Conduct. By participating in this project you agree to abide by its terms.

## Testing Guidelines

- Write tests to cover any new features or bug fixes.
- All test files must be placed within the `tests/` directory with a `.test.ts` or `.test.tsx` extension.

Happy coding!
