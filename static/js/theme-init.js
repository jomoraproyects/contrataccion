try {
  const cookie = document.cookie.match(/(?:^|; )tema=(dark|light)/);
  const preferencia = cookie?.[1] || localStorage.getItem("tema");
  document.documentElement.dataset.bsTheme = preferencia ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
} catch (_) {
  // Se conserva el tema claro si el navegador restringe el almacenamiento.
}
