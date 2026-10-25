import streamlit as st

from analyzer.github_utils import (
    get_repository_info,
    get_repository_files,
)
from analyzer.repository_analyzer import analyze_repository
from analyzer.ai_review import generate_repository_review

st.set_page_config(
    page_title="RepoLens AI",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 RepoLens AI")
st.subheader("Understand any public GitHub repository")
st.write(
    "Explore repository structure, understand its purpose, "
    "and get an AI-powered code review using your local Ollama model."
)

repo_url = st.text_input(
    "GitHub repository URL",
    placeholder="https://github.com/pallets/flask",
)

# --- Step 1: analyze. The result is saved in st.session_state so it survives
# --- the page rerun that Streamlit does every time ANY button is clicked.
if st.button("Analyze Repository", type="primary"):
    if not repo_url.strip():
        st.warning("Please enter a GitHub repository URL.")
    else:
        try:
            with st.spinner("Downloading repository and preparing analysis..."):
                info = get_repository_info(repo_url)
                files = get_repository_files(repo_url)
                report = analyze_repository(files)

            if not files:
                st.error("No readable repository files were found.")
            else:
                st.session_state["analysis"] = {"info": info, "report": report}
                st.session_state.pop("repo_review", None)  # drop the old review
                st.success("Repository downloaded and analyzed!")

        except (ValueError, RuntimeError) as error:
            st.error(str(error))
        except Exception as error:
            st.error(f"Unexpected error: {error}")

# --- Step 2: show results from session_state (outside the Analyze button).
analysis = st.session_state.get("analysis")

if analysis:
    info = analysis["info"]
    report = analysis["report"]

    st.header(info["name"])
    st.write(info["description"])
    st.markdown(f"[Open repository]({info['url']})")

    first, second, third = st.columns(3)
    first.metric("Files analyzed", report["total_files"])
    second.metric("Languages detected", len(report["languages"]))
    third.metric("Source files", len(report["source_files"]))

    st.subheader("Languages")
    if report["languages"]:
        st.bar_chart(report["languages"])
    else:
        st.info("No recognized programming languages found.")

    st.subheader("🤖 AI Repository Summary and Code Review")

    if st.button("Generate AI Review", type="primary"):
        try:
            with st.spinner("Ollama is reviewing the selected repository files..."):
                review = generate_repository_review(
                    {**report, "name": info["name"]}
                )
            st.session_state["repo_review"] = review
        except Exception as error:
            st.error(
                f"Could not generate AI review: {error}. "
                "Check that Ollama is running and llama3.2:3b "
                "is available."
            )

    if st.session_state.get("repo_review"):
        st.markdown(st.session_state["repo_review"])

    with st.expander("Repository file structure"):
        if report["file_tree"]:
            st.code("\n".join(report["file_tree"]))
        else:
            st.info("No readable files were found.")

    with st.expander("Important configuration files"):
        if report["important_files"]:
            for file in report["important_files"]:
                st.markdown(f"**{file['path']}**")
                st.code(file["content"][:8000])
        else:
            st.info("No recognized configuration files were found.")

    with st.expander("README"):
        if report["readme"]:
            st.markdown(report["readme"][:12000])
        else:
            st.info("No README was found in the downloaded files.")

    with st.expander("Browse source code"):
        if report["source_files"]:
            choices = [file["path"] for file in report["source_files"]]
            selected = st.selectbox("Choose a source file", choices)
            selected_file = next(
                file for file in report["source_files"]
                if file["path"] == selected
            )
            st.code(selected_file["content"][:12000])
        else:
            st.info("No source files were found.")

st.divider()
st.caption("RepoLens AI · Local repository analysis project")