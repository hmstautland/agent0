function toggleCvCard() {
  const card = document.getElementById("cv-card");
  const btn = document.querySelector(".cv-btn");
  const opening = card.classList.contains("hidden");

  card.classList.toggle("hidden");
  btn.setAttribute("aria-expanded", String(opening));
}

// A chosen file replaces the textarea's text for that field (the server prefers the file)
function initCvFilePicker(fieldName) {
  const fileInput = document.getElementById(`cv-${fieldName}-file`);
  const label = document.getElementById(`cv-${fieldName}-file-name`);
  const textArea = document.getElementById(`cv-${fieldName}-text`);

  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    label.textContent = file ? `Using file: ${file.name}` : "";
    label.classList.toggle("hidden", !file);
    textArea.disabled = Boolean(file);
  });
}

function showCvError(message) {
  const error = document.getElementById("cv-error");
  error.textContent = message;
  error.classList.toggle("hidden", !message);
}

async function tailorCv() {
  const button = document.getElementById("cv-generate-btn");
  const result = document.getElementById("cv-result");
  const form = new FormData();

  for (const field of ["master", "role"]) {
    const file = document.getElementById(`cv-${field}-file`).files[0];
    if (file) form.append(`${field}_file`, file);
    form.append(`${field}_text`, document.getElementById(`cv-${field}-text`).value);
  }
  form.append("company", document.getElementById("cv-company").value);

  showCvError("");
  result.classList.add("hidden");
  button.disabled = true;
  button.textContent = "Writing... this can take a minute";

  try {
    const response = await fetch("/cv/tailor", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Something went wrong");

    document.getElementById("cv-download-cv").href = data.cv_url;
    document.getElementById("cv-download-letter").href = data.letter_url;
    document.getElementById("cv-preview-cv").textContent = data.cv;
    document.getElementById("cv-preview-letter").textContent = data.letter;
    result.classList.remove("hidden");
  } catch (e) {
    showCvError(e.message);
  } finally {
    button.disabled = false;
    button.textContent = "Tailor CV and cover letter";
  }
}

initCvFilePicker("master");
initCvFilePicker("role");
