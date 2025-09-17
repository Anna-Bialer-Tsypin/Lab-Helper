# File: tools/chunk_summarizer.py

import os
from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.tools import tool
from langchain.docstore.document import Document

@tool("chunk_summarizer")
def chunk_summarizer_tool(chunks: List[str], prompt_template: str) -> str:
    """
    Summarizes a list of text chunks using an LLM and a given prompt template.

    Input: A list of strings (chunks) and a prompt template string.
    Output: A single, consolidated summary string.
    """
    # Set up the LLM model
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.2)

    # Define the prompt
    prompt = PromptTemplate(template=prompt_template, input_variables=["context"])
    llm_chain = LLMChain(prompt=prompt, llm=llm)

    # Combine all chunks into a single context
    context = "\n\n---\n\n".join(chunks)

    # Run the LLM chain to get the summary
    try:
        response = llm_chain.run(context=context)
        return response
    except Exception as e:
        return f"Error during chunk summarization: {e}"