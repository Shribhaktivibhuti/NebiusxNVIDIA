# Vibe Bro 🤙

**AI writes code freshers can't check. Vibe Bro runs it, proves what's broken, and teaches them to catch it themselves.**

Built for the Nebius Global AI Hackathon (Coding & Agentic Engineering track). It is powered by NVIDIA Nemotron models on Nebius Token Factory, with Tavily for live documentation checks.

The Python package is still called `secondlook`, the project's working name.

## What it does

1. **Package check.** Looks up every imported package on PyPI. AI models often invent package names: a USENIX Security 2025 study found 205,474 invented names across 576,000 AI code samples.
2. **Docs check.** Uses Tavily web search, read by Nemotron 3 Nano, to confirm that library calls exist and aren't deprecated (for example `DataFrame.append`, removed in pandas 2.0).
3. **Break it.** Nemotron 3 Super writes pytest tests from what the code was *supposed* to do, including edge cases. Then it runs them in a sandbox.
4. **Learn.** Nemotron 3 Nano explains each failure at a beginner's level: first a question to predict the result, then a hint, then the line, then the fix.

5. **Practice drill.** Short snippets for common fresher tasks, each with one planted AI-typical bug. Find the line and name the bug type, and a skill profile shows which kinds you keep missing.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # add NEBIUS_API_KEY and TAVILY_API_KEY
python -m secondlook.llm           # lists the Nemotron models your key sees and says hello
streamlit run app.py
```

The keys are read from `.env` automatically.

Paste `examples/average_order_value.py` with the intent "Read a CSV of orders (order_id, amount) and return the average order value". It should flag:
- the invented `csv_utils_pro` package,
- the header row counted as an order.

## Practice drill

The **Practice drill** tab shows one snippet at a time. You get a point for finding the buggy line and a point for naming the bug type. The next drill targets the bug type you miss most. If you also explain the bug in your own words, Nemotron 3 Super gives feedback on your explanation.

Every exercise has a hidden test that passes on the fixed code and fails on the buggy code, so every answer is proven. To check them all:

```bash
python -m secondlook.drill
```

`drills/seed.json` holds 14 hand-checked exercises, two per bug type. To add more with Nemotron 3 Ultra:

```bash
python -m secondlook.drill_generator --count 50
```

The generator keeps a candidate only if it passes the hidden-test check, the package check and a few sanity checks. It saves them to `drills/generated.json` and makes at most 3 model calls per exercise kept (change this with `--max-attempts`).

**As a Nebius Serverless Job.** `Dockerfile.drills` packages the generator. Serverless Jobs run on a GPU node billed to Nebius AI Cloud, not to Token Factory credits, and the generator needs no GPU, so running it locally is cheaper. If you do run it as a Job, pass `NEBIUS_API_KEY` as a secret and mount an Object Storage bucket for `--out`, because the job's disk is wiped when it finishes.

## Sandbox

- **On your laptop:** each run happens in a throwaway folder with CPU, memory and time limits. This does **not** block network access or file reads, so only check code you'd be willing to run yourself.
- **Hosted demo:** set `E2B_API_KEY`. Each run then happens in a fresh [E2B](https://e2b.dev) cloud sandbox, which holds none of our API keys and is thrown away afterwards. When the keys come from Streamlit secrets and `E2B_API_KEY` is missing, the app switches tests off instead of running pasted code next to the keys.

## Deploy the demo on Streamlit Community Cloud

1. Get an E2B API key at [e2b.dev](https://e2b.dev). The free Hobby plan comes with credits.
2. At [share.streamlit.io](https://share.streamlit.io), click **Create app**, then pick this repository, its branch, and `secondlook/app.py` as the main file path. You need admin rights on the repository.
3. Open **Advanced settings** and paste the keys into **Secrets**:
   ```toml
   NEBIUS_API_KEY = "your-token-factory-key"
   TAVILY_API_KEY = "your-tavily-key"
   E2B_API_KEY = "your-e2b-key"
   ```
4. Deploy, then paste the example above and check that section 3 shows tests passing and failing.

## NVIDIA and Nebius usage

| Step | Model or service |
|---|---|
| Docs-check reading and beginner explanations | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` |
| Test writing, and feedback on drill explanations | `nvidia/nemotron-3-super-120b-a12b` |
| Drill generation | `nvidia/Nemotron-3-Ultra-550b-a55b`, locally or as a Nebius Serverless Job |
| All model calls | Nebius Token Factory, `https://api.tokenfactory.nebius.com/v1/` |
| Running pasted code and its tests in the hosted demo | E2B cloud sandboxes |

## License

MIT
