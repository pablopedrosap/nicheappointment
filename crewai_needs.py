import csv
import json
import os
import re
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
from crewai_tools import SerperDevTool, ScrapeWebsiteTool

# Setting environment variables for API keys
os.environ["OPENAI_API_KEY"] = "OPENAI_API_KEY_REDACTED"
os.environ["SERPER_API_KEY"] = "88ae5974658b41cd2af65d4064455f9b9b3f57e4"
os.environ['CLAUDE_API_KEY'] = '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'

llm4o = ChatOpenAI(model="gpt-4o")
llm4o_mini = ChatOpenAI(model="gpt-4o-mini")


def create_query_generator_agent():
    return Agent(
        role='Query Generator',
        goal='Generate detailed and specific search queries based on the given niche to find relevant business websites. Divide the location and provide slight variations of the niche name for better findings in google maps.',
        backstory='You generate highly effective search queries to discover pertinent business websites within the specified niche. Your expertise in crafting precise queries ensures comprehensive results.',
        tools=[],
        verbose=True,
        llm=llm4o_mini
    )


def queries_leads(niche, location):
    query_generator = create_query_generator_agent()

    def the_query_task(niche, location):
        '''{round(TARGET_EMAIL_COUNT/20, ndigits=-1) + 1}'''
        return Task(
            description=f'Generate 15 search queries specifically relevant to the niche: {niche}. The queries should be separated in niche and zone designed to find business websites within this niche in google maps (be smart about niche and zone so more businesses should appear). divide the location: {location}, into zones within it followed by the given location, *example: (Sevilla, España)*'
                        f'also slightly variate the niche name for better findings in google maps.',
            agent=query_generator,
            expected_output='Only respond with this, nothing before or after -> [{"niche": "...", "zone": "..."}, {"niche": "...", "zone": "..."}, ... as many as number of queries ...]'
        )

    query_task = the_query_task(niche, location)
    crew = Crew(
        agents=[query_generator],
        tasks=[query_task],
        verbose=True
    )
    crew_output = str(crew.kickoff())

    queries = json.loads(crew_output)
    print(queries)
    return queries
