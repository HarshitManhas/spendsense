def main() -> None:
    import uvicorn
    uvicorn.run("ai_expense_scanner.api:app", host="127.0.0.1", port=8000)
