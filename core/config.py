# Chunking Stuff
CHUNK_SIZE = 80

# Prompts
CLEANUP_SYSTEM_PROMPT = "You are a helpful assistant cleaning up a transcript for an intelligent reader."
CLEANUP_USER_PROMPT = """
Summarize the following transcript chunk. Understand that the speaker or speakers may have rambled and taken a little bit to get to their points.
Summarize as if your summary were then going to be summarized as part of an overall summary of what was talked about in this audio clip.
Make a good faith attempt to understand both the letter and the gist of what's being said, and be precise in your speech. Summarize in bullet points.
Make a bullet point out of every major and medium sized point made by the speaker or speaker. Don't summarize the discussion -- summarize what each person said and meant.
I'm ok if the summaries are long. Return only the summary, no addtional commentary or context.
"""