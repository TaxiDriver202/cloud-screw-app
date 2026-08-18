from functools import lru_cache
from os import getenv

from openai import OpenAI
from pydantic import BaseModel, Field


class AnalysisException(Exception):
    """Analysis goofed"""


class AnalysisOutput(BaseModel):
    deviation: bool = Field(
        description="Whether or not the weather data shows severe deviations"
    )
    analysis: str = Field(description="Analysis of the weather data")


@lru_cache(maxsize=1)
def get_client() -> OpenAI | None:
    try:
        client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
        return client
    except Exception as e:
        print(f"Failed to create openai client: {e}")
        return None


def analyze_trends(data: str) -> AnalysisOutput:
    """Analyzes weather data from a CSV-formatted string of readings.
    @return AnalysisOutput
    @raises AnalysisException if the analysis could not be produced"""
    client = get_client()
    if client is None:
        raise AnalysisException("OpenAI client is not configured")
    try:
        res = client.responses.parse(
            model="gpt-5.6-luna",
            instructions="""
            You are a agent that analyzes weather data from bluetooth sensors.
            Synthesize the data you receive and identify trends in the data,
            for example large fluctuations or deviations from the norm.
            If there is nothing out of the ordinary, answer with some simple
            observation about the data in a kind way.
            """,
            input=[{"role": "user", "content": data}],
            text_format=AnalysisOutput,
        )
    except Exception as e:
        raise AnalysisException(f"Analysis request failed: {e}") from e
    if res.error is not None:
        raise AnalysisException(res.error.message)
    if res.output_parsed is None:
        raise AnalysisException("Failed to parse analysis output")
    return res.output_parsed
