// Push-to-talk recording for the mic button (wired via onclick in index.html)

let mediaRecorder;
let audioChunks = [];
let recording = false;

async function toggleRecording() {
  if (!recording) {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
    });

    mediaRecorder = new MediaRecorder(stream);

    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.start();

    recording = true;

    document.querySelector(".mic-btn").innerText = "⏹";
  } else {
    mediaRecorder.stop();

    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks);

      const formData = new FormData();
      formData.append("file", blob, "audio.wav");

      const res = await fetch("/speech", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      document.getElementById("input").value = data.text;
    };

    recording = false;

    document.querySelector(".mic-btn").innerText = "🎤";
  }
}
