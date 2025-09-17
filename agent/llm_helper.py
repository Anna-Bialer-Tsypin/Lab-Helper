# File: db/llm_helper.py
import os
import sys
from typing import List, Optional
from langchain.docstore.document import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain


def summarize_guidance(question: str, docs: List[Document], prompt_template: Optional[str] = None) -> str:
    """
    Summarizes the retrieved document chunks using the Gemini API via LangChain.
    Can use a custom prompt template.
    """
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.2)

    # Use a default prompt if none is provided
    # THIS PROMPT IS NOW UPDATED TO BE MORE EXPLICIT
    if not prompt_template:
        prompt_template = """
        You are a safety assistant. Your task is to provide a concise summary of the guidance for a material.
        Use only the following context to answer the question. Do not use outside knowledge.
        If the context does not contain the information, state that you cannot provide an answer.

        Context:
        {context}

        Question:
        {question}

        Summary:
        """

    # We now override the mixture prompt directly in the mixture_builder.py
    # This keeps the `llm_helper` generic, which is good practice.
    # The new mixture prompt will be passed into this function from the Streamlit app.
    prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
    llm_chain = LLMChain(prompt=prompt, llm=llm)

    context = "\n\n---\n\n".join([d.page_content for d in docs])

    try:
        return llm_chain.run(context=context, question=question)
    except Exception as e:
        return f"An error occurred while generating a response: {e}"