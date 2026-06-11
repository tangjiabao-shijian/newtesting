from neo4j import GraphDatabase

URI = "neo4j://localhost:7687"
AUTH = ("neo4j", "12345678")

def get_person_info_by_name(name):
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        result, _, _ = driver.execute_query(
            """
            MATCH (n:Person {name: $name}) RETURN n
            """,
            database_="neo4j",
            parameters_={"name": name}
        )
        person_info = []
        for record in result:
            person_node = record["n"]
            person_info.append({
                "name": person_node.get("name"),
                "gender": person_node.get("gender")
            })
        return person_info
    
if __name__ == "__main__":
    name_to_query = "刘德华"
    info = get_person_info_by_name(name_to_query)
    print(f"Information for {name_to_query}: {info}")