# File: pages/01_Chat.py

import streamlit as st
import uuid
import datetime
from agent.chat_agent import get_graph_agent


# --- Streamlit Chat UI ---
def main():
    st.set_page_config(page_title="Lab Safety Agent 🤖", page_icon="🧪")
    st.title("Lab Safety Agent 🧪")
    st.caption(
        "I'm a conservative lab safety assistant. Ask me questions about lab safety, especially from SDS documents.")

    # Add a sidebar to manage conversations and LLM selection
    with st.sidebar:
        st.subheader("Configuration")

        # LLM selection dropdown
        llm_options = ["gemini-1.5-flash", "gpt-3.5-turbo", "llama3"]
        selected_llm = st.selectbox("Choose LLM", options=llm_options)

        st.markdown("---")
        st.subheader("Conversations")
        if st.button("Start New Chat", use_container_width=True):
            st.session_state.clear()
            st.session_state.messages = []
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.selected_llm = selected_llm
            st.rerun()

        st.markdown("---")
        st.write("Current Chat ID:")
        st.code(st.session_state.get("thread_id", "No Chat Active"))

    # --- Main Application Logic ---

    # Initialize agent and conversation state if not already done
    if "agent" not in st.session_state or st.session_state.get("selected_llm") != selected_llm:
        st.session_state.agent = get_graph_agent(selected_llm)
        st.session_state.selected_llm = selected_llm
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []

    st.session_state.config = {"configurable": {"thread_id": st.session_state.thread_id}}

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # React to user input
    if prompt := st.chat_input("What's on your mind?"):
        with st.chat_message("user"):
            st.markdown(prompt)

        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    # **FIXED:** Pass the entire messages history to the agent
                    response = st.session_state.agent.invoke(
                        {"messages": st.session_state.messages},
                        st.session_state.config
                    )
                    assistant_response = response['messages'][-1].content
                    st.markdown(assistant_response)
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    assistant_response = "I'm sorry, an error occurred. Please try again."

        st.session_state.messages.append({"role": "assistant", "content": assistant_response})


if __name__ == "__main__":
    main()