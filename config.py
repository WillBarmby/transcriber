from pathlib import Path

# Directories
INPUT_DIR = Path.home() / "Downloads"
OUTPUT_DIR = Path.home() / "Python-Projects/watch_and_transcribe/file_folders/wav_files"
TEXT_DIR = Path.home() / "Python-Projects/watch_and_transcribe/file_folders/llama"
FINAL_DIR = Path.home() / "Python-Projects/watch_and_transcribe/file_folders/final"
ARCHIVE_DIR = Path.home() / "Python-Projects/watch_and_transcribe/file_folders/archive"


# Whisper Stuff
MODEL_PATH = Path("/Users/willbarmby/Tools/whisper.cpp/models/ggml-medium.en.bin")
WHISPER_CLI_PATH = Path("/Users/willbarmby/Tools/whisper.cpp/build/bin/whisper-cli")

# Chunking Stuff
CHUNK_SIZE = 80

# Llama Prompts
LLAMA_MODEL_PATH = "/Users/willbarmby/Tools/llama_models/3.1-8B/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
# "/Users/willbarmby/Tools/llama_models/llama-3.2-3b-instruct-q4_k_m.gguf"
CLEANUP_SYSTEM_PROMPT = "You are a helpful assistant cleaning up a transcript for an intelligent reader."
CLEANUP_USER_PROMPT = """
Summarize the following transcript chunk. Understand that the speaker or speakers may have rambled and taken a little bit to get to their points.
Summarize as if your summary were then going to be summarized as part of an overall summary of what was talked about in this audio clip.
Make a good faith attempt to understand both the letter and the gist of what's being said, and be precise in your speech. Summarize in bullet points.
Make a bullet point out of every major and medium sized point made by the speaker or speaker. Don't summarize the discussion -- summarize what each person said and meant.
I'm ok if the summaries are long. Return only the summary, no addtional commentary or context.
"""


SUMMARY_PROMPT = """take the following chunk summaries and summarize the whole podcast."""




TEST_TEXT = """
 (upbeat music)
 I'm Kyle Newport, and this is "Deep Questions,"
 the show about cultivating a deep life
 in a distracted world.
 So I'm here in my Deep Work HQ joined as always
 by my producer, Jesse.
 Jesse, I have a question for you.
 Have you at any point ever used AI
 to help you while you were writing something?
 - No, a lot of people have been asking you this though.
 - Have been asking me or been asking you?
 - You. - Yeah.
 - Through email.
 - This I think is the point.
 Most people right now know about tools like ChatGPT,
 but are not actively using them for things
 like to help their writing, but more and more people are.
 It's this sort of growing movement.
 This is what we're gonna get into into our deep dive today.
 There's a blockbuster new article
 that came out of the MIT Media Lab
 that did some really interesting experiments
 to figure out what happens when you're writing with AI,
 what is the impact on deep work?
 So that's coming up.
 I'm gonna have a special surprise guest join me
 to help me dissect that article
 and understand this relationship between deep work and AI.
 So that should be fun, Jesse.
 Then we've got questions,
 including a really good case study
 where you're gonna get a sort of bullet point description
 of the systems for time management and attention management
 that this particular individual do.
 And I think it's a really smart system
 for those looking for the deep life so that you'll like it.
 And then our final segment,
 I'm gonna do a twist on my normal what I'm reading segment.
 I'm adding a twist to it, what I'm not reading.
 This is just an excuse, Jesse,
 for me to rant about something
 that has been bothering me recently.
 I will preview more importantly,
 we have a little bit more Cal Network art
 in that final segment.
 This time, a completely un-doctored photo.
 So we should look forward to that.
 If you stick around for anything,
 it is to see the next beautiful piece of Cal Network art.
 So we've got a lot to do.
 So I think we should just get rolling
 and start with our deep dive.
 So last month, Ezra Klein went on the How I Write podcast.
 The host, David Perel, asked Ezra
 about using AI for his writing.
 And Ezra's answer generated some controversy.
 It began when Ezra said the following, and I quote,
 "I think it is very dangerous to use chat GPT
 "in any serious way for writing."
 Ezra then goes on to give some reasons for this claim.
 One of the reasons is that AI can help you rewrite
 or polish or check what you've written,
 but I can't tell you if the ideas itself are good or not.
 As Ezra elaborates, you have to be attuned
 to that voice in you.
 It's like, not right, not right, not right, not right.
 You're not trying to bypass that or get around it
 or get to where it's soft.
 You're trying to get to the point where you're like,
 ah, got it right.
 And that's usually intellectual labor.
 Ezra later adds, chat GPT can't identify
 fundamentally wrong ideas.
 When later asked specifically about AI and journalism,
 Ezra says, "I'm not completely against anything,
 "and I have not, and not for lack of trying,
 "and I think not for lack of being informed
 "or interested in the issue,
 "found a way that I consistently use AI in my work.
 "I'll sometimes use it right now
 "as your replacement for Google searches,
 "and it's valuable for that."
 A lot of people appreciated Ezra's points,
 but some people, including several I know
 and who wrote into the show,
 thought that his stance was nostalgic and out of touch,
 like sticking with a typewriter
 in the age of word processors.
 A few cranky people might do it,
 but it's basically just a worse process
 that makes you slower at your craft.
"""