(function () {
  function clearError(textarea) {
    textarea.classList.remove("json-invalid");
    var sib = textarea.parentNode.querySelector(".json-error");
    if (sib) sib.remove();
  }

  function showError(textarea, message) {
    textarea.classList.add("json-invalid");
    var existing = textarea.parentNode.querySelector(".json-error");
    if (existing) existing.remove();
    var div = document.createElement("div");
    div.className = "json-error";
    div.textContent = "Invalid JSON: " + message;
    textarea.parentNode.appendChild(div);
  }

  function validateForm(form) {
    var fields = form.querySelectorAll("textarea.code-input");
    var ok = true;
    fields.forEach(function (ta) {
      var value = ta.value.trim();
      if (!value) {
        clearError(ta);
        return;
      }
      try {
        JSON.parse(value);
        clearError(ta);
      } catch (e) {
        showError(ta, e.message);
        ok = false;
      }
    });
    return ok;
  }

  function injectFileLoader(textarea) {
    if (textarea.dataset.fileLoaderAttached) return;
    textarea.dataset.fileLoaderAttached = "true";
    var loader = document.createElement("label");
    loader.className = "json-file-loader";
    loader.innerHTML = '<span>Load from JSON file</span><input type="file" accept=".json,application/json" />';
    var input = loader.querySelector("input");
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function (e) {
        var text = e.target.result;
        try {
          var parsed = JSON.parse(text);
          textarea.value = JSON.stringify(parsed, null, 2);
          clearError(textarea);
        } catch (err) {
          textarea.value = text;
          showError(textarea, err.message);
        }
        input.value = "";
      };
      reader.readAsText(file);
    });
    textarea.parentNode.insertBefore(loader, textarea);
  }

  function attach(root) {
    var forms = (root || document).querySelectorAll("form");
    forms.forEach(function (form) {
      if (form.dataset.jsonValidateAttached) return;
      form.dataset.jsonValidateAttached = "true";
      form.addEventListener("submit", function (event) {
        if (!validateForm(form)) event.preventDefault();
      });
      // For htmx-submitted forms: htmx sends its own request; cancel it
      form.addEventListener("htmx:beforeRequest", function (event) {
        if (!validateForm(form)) event.preventDefault();
      });
      form.addEventListener("input", function (event) {
        if (event.target.matches && event.target.matches("textarea.code-input")) {
          clearError(event.target);
        }
      });
      form.querySelectorAll("textarea.code-input").forEach(injectFileLoader);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { attach(); });
  } else {
    attach();
  }

  // Re-attach to forms swapped in via htmx
  document.body && document.body.addEventListener("htmx:afterSwap", function (event) {
    attach(event.target);
  });
})();
