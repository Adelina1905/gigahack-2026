function App() {
  return (
    <main className="min-h-screen bg-background-secondary p-8">
      <div className="mx-auto max-w-2xl rounded-lg border border-border bg-background p-8">
        <h1 className="text-4xl font-bold text-primary">Tailwind is ready</h1>
        <p className="mt-4 text-md text-text-muted">
          Theme tokens from <code>tailwind.config.ts</code> are available as utility classes.
        </p>
        <div className="mt-6 flex gap-3">
          <button className="rounded-md bg-primary px-4 py-2 font-semibold text-text-inverted hover:bg-primary-dark">
            Primary
          </button>
          <button className="rounded-md bg-accent px-4 py-2 font-semibold text-text hover:bg-accent-dark">
            Accent
          </button>
          <span className="rounded-md bg-success-light px-3 py-2 text-sm text-success">Success</span>
          <span className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger">Danger</span>
        </div>
      </div>
    </main>
  )
}

export default App
