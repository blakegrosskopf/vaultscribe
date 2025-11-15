# AI API Class/File

## Included files
In order to use this script, you must have the following:
./Ai_API.py (the script)
./whisper (the whisper directory must be a subdirectory of the directory where Ai_API.py is located)
./whisper/tiny.pt
./transcription_test.wav
ffmpeg (in any directory of your chosing, so long as ffmpeg's /bin directory has been added to the system PATH)

## Installing dependencies
Included is a requirements.txt, showing the pip-downloadable dependencies and some of their minimum versions. You may chose to install
them with:
pip install -r requirements.txt

If the command runs successfully, then all you have left to do is to add the /bin folder of ffmpeg (audio tool whisper uses during
transcription) to the PATH environment variable of your computer (assuming you have Windows -- if you have Mac, I trust you to know
the correct place for the binaries and such). As we are only prototyping in this class, it isn't a big deal that we have to install
ffmpeg manually; of course, in production, the app would automatically create the PATH entry and such.

## What does the code do?
In short, it uses OpenAI's open source transcription model Whisper (specifically, the "tiny" variant) to receive a filepath to an audio
file, transcribe the file, and then return that transcription as a string. It can also receive a string and make a call to OpenRouter
(a service that hosts LLMs for free, albeit with some data privacy catches), which returns a summary of the string. Because OpenRouter
allows the companies that host the LLMs to give away the data that is sent via OpenRouter: 1) don't send private information during
testing, and 2) we will have to have a writeup section detailing how, in the real thing/production environment, we would work out
a privacy agreement with OpenAI (somewhat of a common occurrence) and use their models to keep sensitive data more protected (and that
we are simply using the free options during our demonstrations, even though there is no meaningful difference in the quality of the
summaries).

## Using the file
To use the file simply import it into the app's main script, create an object of the AISummarizerTranscriber class (as shown within __main__ of Ai_API.py), and pass in filepaths to audio files or string representations of the transcriptions as needed.
Again, __main__ shows exactly what is required to make calls to the script.

When you do run the __main__ function (for testing), you should see output like this (note a couple warnings from whisper are ok):

C:\Users\boudr\OneDrive\Documents\Word, Powerpoint, etc. docs\SMU\SMU Senior Fall 2025\Ethical Issues in Computing\Project Part 3 Code>python Ai_API.py
Working...

C:\Users\boudr\AppData\Local\Programs\Python\Python312\Lib\site-packages\whisper\transcribe.py:132: UserWarning: FP16 is not supported on CPU; using FP32 instead
  warnings.warn("FP16 is not supported on CPU; using FP32 instead")
TRANSCRIPT:
 Hello, this is a test recording. I am going to say all of the numbers between 1 and 10, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10. Therefore, I am now done with this test.

SUMMARY:
 The speaker counts from one to ten and then states that they have completed the test.

C:\Users\boudr\OneDrive\Documents\Word, Powerpoint, etc. docs\SMU\SMU Senior Fall 2025\Ethical Issues in Computing\Project Part 3 Code>pause
Press any key to continue . . .


## NOTES
- You might have to run the call to Ai_API.py in a separate thread from the one that processes GUI logic, that way the GUI can respond
to a user's request (pressing a button) to stop the transcription part-way through.

- The OpenRouter account/token is for a free account. These accounts are rate limited to 50 API calls (aka summaries) per day, and
a limited (but varying) number of calls per minute. In other words, try to avoid spamming API calls while testing, especially if
the in-class demonstration day is coming near.