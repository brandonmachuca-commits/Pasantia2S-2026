window.mostrarMensaje = function (texto, tipo = "loading") {
    const resultado = document.getElementById("resultado");
    resultado.innerHTML = `<div class="${tipo}">${texto}</div>`;
};

window.cargarEstado = async function () {
    try {
        const res = await fetch("/health");
        const data = await res.json();
        document.getElementById("estado").innerHTML = `
            <b>Estado:</b> ${data.status}<br>
            <b>Agentes:</b> ${data.agentes.join(", ")}<br>
            <b>Último tema:</b> ${data.historial_activo ?? "-"}
        `;
    } catch {
        document.getElementById("estado").innerHTML =
            "<span class='error'>No se pudo obtener el estado.</span>";
    }
};

window.actualizar = async function (categoria) {
    window.mostrarMensaje(`Actualizando ${categoria}...`);
    try {
        const res = await fetch(`/admin/update/${categoria}`, { method: "POST" });
        const data = await res.json();
        if (data.ok) {
            window.mostrarMensaje(`✅ ${data.mensaje}`, "success");
            window.cargarEstado();
        } else {
            window.mostrarMensaje(data.error, "error");
        }
    } catch (e) {
        window.mostrarMensaje(e.message, "error");
    }
};

document.addEventListener("DOMContentLoaded", function () {
    // Inicializar estado
    window.cargarEstado();

    // Botón "Actualizar TODO"
    document.getElementById("updateAll").addEventListener("click", async function () {
        window.mostrarMensaje("Actualizando todo...");
        try {
            const res = await fetch("/admin/update/all", { method: "POST" });
            const data = await res.json();
            if (data.ok) {
                window.mostrarMensaje(`✅ ${data.mensaje}`, "success");
                window.cargarEstado();
            } else {
                window.mostrarMensaje(data.error, "error");
            }
        } catch (e) {
            window.mostrarMensaje(e.message, "error");
        }
    });

    // Botones individuales
    document.querySelectorAll("[data-cat]").forEach(function (boton) {

        boton.addEventListener("click", function () {

            const categoria = this.dataset.cat;

            window.actualizar(categoria);

        });

    });

    // Botón "Recargar agentes"
    document.getElementById("reloadBtn").addEventListener("click", async function () {
        window.mostrarMensaje("Recargando agentes...");
        try {
            const res = await fetch("/admin/reload", { method: "POST" });
            const data = await res.json();
            if (data.ok) {
                window.mostrarMensaje(`✅ ${data.mensaje}`, "success");
                window.cargarEstado();
            } else {
                window.mostrarMensaje(data.error, "error");
            }
        } catch (e) {
            window.mostrarMensaje(e.message, "error");
        }
    });
});