const canvas = document.getElementById("starfield");
const ctx = canvas.getContext("2d");

canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

const stars = [];
const STAR_COUNT = 600;

for (let i = 0; i < STAR_COUNT; i++) {
  stars.push({
    x: Math.random() * canvas.width - canvas.width / 2,
    y: Math.random() * canvas.height - canvas.height / 2,
    z: Math.random() * canvas.width,
  });
}

function animate() {
  ctx.fillStyle = "black";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (let star of stars) {
    star.z -= 8;

    if (star.z <= 0) {
      star.z = canvas.width;
    }

    const x = (star.x / star.z) * canvas.width;
    const y = (star.y / star.z) * canvas.width;

    const radius = (1 - star.z / canvas.width) * 3;

    ctx.beginPath();
    ctx.fillStyle = "white";
    ctx.arc(
      x + canvas.width / 2,
      y + canvas.height / 2,
      radius,
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }

  requestAnimationFrame(animate);
}

animate();

window.addEventListener("resize", () => {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
});
