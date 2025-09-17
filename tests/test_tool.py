# File: test_tool.py

# Import the function you want to test
from agent.agent_tools.property_summarizer import get_material_properties

# You will also need to import the core database query function
from db.query import smart_search

# And the vectorstore to initialize your database connection
from db.schema import get_vectorstore


def debug_tool():
    """
    A simple function to test the tool in isolation.
    """
    material1 = "Hydrochloric Acid"
    material2 = "Sodium hypochlorite solution"

    print("--- Starting Tool Test ---")

    # Initialize the database connection (this is important)
    vdb = get_vectorstore()

    # Test the first material
    print(f"\nTesting properties for: {material1}")
    result1 = get_material_properties(material1)
    print(f"Tool returned: {result1}")

    # Test the second material
    print(f"\nTesting properties for: {material2}")
    result2 = get_material_properties(material2)
    print(f"Tool returned: {result2}")

    print("\n--- Test Complete ---")
def debug_smart_search():
    print("--- Testing smart_search function directly ---")

    # Test a direct query for one of the materials
    vdb = get_vectorstore()
    query = "Hydrochloric Acid hazards identification"

    print(f"Searching for query: '{query}'")

    # The key is to pass the locked_material argument
    results = smart_search(query, k=2, locked_material="Hydrochloric Acid")

    print(f"Found {len(results)} documents.")
    if results:
        for doc in results:
            print(f"  - Document found: {doc.metadata.get('material_name')} - {doc.metadata.get('section_name')}")
    else:
        print("  - No documents found.")


def debug_smart_search_with_correct_name():
    print("--- Testing smart_search function with correct name ---")

    # Use the exact name from the database list
    vdb = get_vectorstore()
    query = "Hydrochloric Acid - HCl hazards identification"

    print(f"Searching for query: '{query}'")

    # The locked_material parameter must be the exact database name
    results = smart_search(query, k=2, locked_material="Hydrochloric Acid - HCl")

    print(f"Found {len(results)} documents.")
    if results:
        for doc in results:
            print(f"  - Document found: {doc.metadata.get('material_name')} - {doc.metadata.get('section_name')}")
    else:
        print("  - No documents found.")


if __name__ == "__main__":
    debug_smart_search_with_correct_name()
    # debug_tool()

    # debug_smart_search() # Run this instead