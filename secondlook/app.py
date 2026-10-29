"""Vibe Bro web app: paste AI-written code, get proof of what's broken, learn the fix."""

import os

import streamlit as st

from secondlook import drill, sandbox
from secondlook.pipeline import second_look

SECRET_NAMES = ("NEBIUS_API_KEY", "TAVILY_API_KEY", "E2B_API_KEY")


def load_hosted_secrets():
    """On Streamlit Community Cloud the keys come from the app's Secrets settings, not .env."""
    try:
        hosted = {name: st.secrets[name] for name in SECRET_NAMES if name in st.secrets}
    except Exception:  # no secrets.toml: running locally with keys from .env
        return
    os.environ.update(hosted)
    if hosted:
        # Tells the sandbox never to run pasted code on this server, next to the keys.
        os.environ["SECONDLOOK_HOSTED"] = "1"


st.set_page_config(page_title="Vibe Bro", page_icon="🤙", layout="wide")
load_hosted_secrets()
st.title("Vibe Bro 🤙")
st.caption("Vibe-coded it? Let Vibe Bro check it before you trust it.")

check_tab, drill_tab = st.tabs(["Check AI code", "Practice drill"])


def check_screen():
    s = st.session_state
    intent = st.text_area("What did you ask the AI to do?", placeholder="Read a CSV of orders and return the average order value")
    code = st.text_area("Paste the code the AI gave you", height=300)
    check_docs = st.checkbox("Check library calls against current docs (Tavily)", value=bool(os.environ.get("TAVILY_API_KEY")))

    if st.button("Take a second look", type="primary", disabled=not code.strip()):
        with st.status("Checking...", expanded=True) as status:
            st.write("Checking packages on PyPI, writing tests, running them in a sandbox...")
            s.report = second_look(code, intent, check_docs=check_docs)
            status.update(label="Done", state="complete")
        s.checked_code = code
        s.check_id = s.get("check_id", 0) + 1
        s.recheck = None

    if s.get("report"):
        show_report(s.report)


def show_report(report):
    s = st.session_state
    for warning in report.warnings:
        st.warning(warning)

    if report.syntax_error:
        st.error(f"This code doesn't run at all: Python can't read {report.syntax_error}.")
        show_explanations(report)
        return

    st.subheader("1. Do the packages exist?")
    if not report.packages:
        st.write("Only the standard library is used.")
    for p in report.packages:
        (st.success if p.exists else st.error)(f"`{p.module}`: {p.detail}")

    if report.calls:
        st.subheader("2. Are the library calls current?")
        for c in report.calls:
            ok = c.get("status") in ("ok", "unsure")
            (st.info if ok else st.warning)(f"`{c['call']}`: {c.get('explanation', '')} {c.get('source_url', '')}")

    st.subheader("3. Does it survive our tests?")
    run = report.run
    if run is None:
        st.info("No tests this time, because writing them was skipped (see the note at the top).")
    else:
        show_run(run)
        with st.expander("Tests Vibe Bro wrote"):
            st.code(report.tests, language="python")

    st.subheader("4. Learn the fix")
    show_explanations(report)

    if run is None:
        return
    st.subheader("5. Fix it and re-check")
    st.caption("Edit the code below, then run the same tests again. When they all pass, you've fixed it.")
    fixed = st.text_area("Your fixed code", value=s.checked_code, height=300, key=f"fixed-{s.check_id}")
    if st.button("Re-run the same tests"):
        with st.spinner("Running the tests in the sandbox..."):
            s.recheck = sandbox.run_tests(fixed, report.tests)
    if s.get("recheck"):
        if not (s.recheck.failed or s.recheck.timed_out or s.recheck.crashed) and s.recheck.passed:
            st.balloons()
            st.success(f"All {s.recheck.passed} tests pass now. Nice fix!")
        else:
            show_run(s.recheck)


def show_run(run):
    if run.timed_out:
        st.error("The code ran too long and was stopped. Look for a loop that never ends.")
    elif run.crashed:
        st.error("The tests couldn't run at all. See the test output below.")
    else:
        st.metric("Tests passed", f"{run.passed} / {run.passed + run.failed}")
        failing = sandbox.failing_tests(run.output)
        if failing:
            st.write("Failing tests: " + ", ".join(f"`{name}`" for name in failing))
    with st.expander("Test output"):
        st.code(run.output[-5000:])


def show_explanations(report):
    if not report.explanations and report.warnings:
        st.info("Nothing to explain from the steps that ran.")
    elif not report.explanations:
        st.success("No problems found. Still read the tests: they show what was checked.")
    for i, e in enumerate(report.explanations, 1):
        st.markdown(f"**Problem {i}: {e.get('bug_type', 'bug')}**")
        st.write("Predict first: " + e.get("predict_question", ""))
        with st.expander("Hint"):
            st.write(e.get("hint", ""))
        with st.expander("Show the line"):
            st.code(e.get("line", ""), language="python")
        with st.expander("Show the fix"):
            st.write(e.get("fix", ""))


@st.cache_data
def exercises():
    return drill.load_exercises()


def drill_screen():
    all_exercises = exercises()
    if not all_exercises:
        st.warning("No drill exercises found in the drills folder.")
        return
    by_id = {e["id"]: e for e in all_exercises}
    s = st.session_state
    s.setdefault("drill_history", [])
    s.setdefault("drill_result", None)
    profile = drill.skill_profile(s.drill_history)
    if s.get("drill_current") not in by_id:
        seen = {a["id"] for a in s.drill_history}
        s.drill_current = drill.next_exercise(all_exercises, seen, profile)["id"]
    ex = by_id[s.drill_current]
    lines = ex["code"].splitlines()

    st.markdown(f"**Someone asked a chatbot:** {ex['task']}")
    st.caption("The code it gave back has one bug of a kind AI often makes. Find the line and name the bug.")
    st.code(ex["code"], language="python", line_numbers=True)

    with st.form(f"answer-{ex['id']}-{len(s.drill_history)}"):
        line = st.selectbox("Which line has the bug?", range(1, len(lines) + 1), format_func=lambda n: f"{n}: {lines[n - 1].strip()}")
        bug_type = st.radio("What kind of bug is it?", drill.BUG_TYPES)
        why = st.text_area("Optional: explain the bug in your own words")
        submitted = st.form_submit_button("Check my answer", type="primary")

    if submitted and s.drill_result is None:
        result = drill.grade(ex, line, bug_type)
        s.drill_history.append({"id": ex["id"], "bug_type": ex["bug_type"], **result})
        s.drill_result = dict(result, why=why.strip())
        if why.strip() and os.environ.get("NEBIUS_API_KEY"):
            try:
                s.drill_result["feedback"] = drill.feedback(ex, why.strip())
            except Exception as e:
                s.drill_result["feedback"] = {"verdict": "", "feedback": f"Couldn't get feedback right now ({type(e).__name__})."}
        profile = drill.skill_profile(s.drill_history)

    result = s.drill_result
    if result:
        bug_lines = ", ".join(map(str, ex["bug_lines"]))
        (st.success if result["line_ok"] else st.error)(
            "You found the line." if result["line_ok"] else f"Not quite: the bug is on line {bug_lines}."
        )
        (st.success if result["type_ok"] else st.warning)(
            f"Bug type: {ex['bug_type']}." if result["type_ok"] else f"The bug type is **{ex['bug_type']}**."
        )
        st.info(ex["explanation"])
        if result.get("feedback"):
            fb = result["feedback"]
            st.markdown(f"**Feedback on your explanation{' (' + fb['verdict'] + ')' if fb.get('verdict') else ''}:** {fb.get('feedback', '')}")
        elif result["why"]:
            st.caption("Add NEBIUS_API_KEY to get Nemotron feedback on your explanation.")
        with st.expander("Show the fixed code"):
            st.code(ex["fixed"], language="python")
        with st.expander("Show the hidden test that proves it"):
            st.code(ex["test"], language="python")
        if st.button("Next drill", type="primary"):
            s.drill_result = None
            s.drill_current = None
            st.rerun()

    if s.drill_history:
        st.divider()
        st.subheader("Your skill profile")
        points = sum(a["line_ok"] + a["type_ok"] for a in s.drill_history)
        st.metric("Score", f"{points} / {2 * len(s.drill_history)}", help="1 point for the line, 1 for the bug type")
        st.write(drill.profile_summary(profile))
        for bug_type in drill.BUG_TYPES:
            if bug_type in profile:
                caught, seen = profile[bug_type]
                st.progress(caught / seen, text=f"{bug_type}: caught {caught} of {seen}")


with check_tab:
    check_screen()
with drill_tab:
    drill_screen()
