// Sign in / create account.

import { post, setToken } from "../api.js";
import { brandMark, h } from "../dom.js";

export function renderAuth(root, info, onSuccess) {
  let mode = "login";
  const error = h("p", { class: "form-error", role: "alert", hidden: true });
  const username = h("input", { type: "text", name: "username", autocomplete: "username", required: true });
  const email = h("input", { type: "email", name: "email", autocomplete: "email" });
  const password = h("input", { type: "password", name: "password", autocomplete: "current-password", required: true });
  const submit = h("button", { class: "btn primary", type: "submit" });
  const usernameLabel = h("span", { text: "Username or email" });
  const emailField = h("label", { class: "field" }, "Email", email);
  const passwordHint = h("span", { class: "hint", text: "At least 8 characters" });
  const loginTab = h("button", { type: "button", text: "Sign in", onclick: () => setMode("login") });
  const registerTab = h("button", { type: "button", text: "Create account", onclick: () => setMode("register") });

  function setMode(next) {
    mode = next;
    const registering = mode === "register";
    loginTab.classList.toggle("current", !registering);
    registerTab.classList.toggle("current", registering);
    emailField.hidden = !registering;
    email.required = registering;
    passwordHint.hidden = !registering;
    usernameLabel.textContent = registering ? "Username" : "Username or email";
    password.autocomplete = registering ? "new-password" : "current-password";
    password.minLength = registering ? 8 : 1;
    submit.textContent = registering ? "Create account" : "Sign in";
    error.hidden = true;
  }

  const form = h(
    "form",
    { class: "stack", novalidate: false },
    h("label", { class: "field" }, usernameLabel, username),
    emailField,
    h("label", { class: "field" }, "Password", passwordHint, password),
    error,
    submit,
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    error.hidden = true;
    try {
      const body =
        mode === "register"
          ? { username: username.value.trim(), email: email.value.trim(), password: password.value }
          : { username: username.value.trim(), password: password.value };
      const data = await post(mode === "register" ? "/auth/register" : "/auth/login", body);
      setToken(data.access_token);
      onSuccess(data.user);
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    } finally {
      submit.disabled = false;
    }
  });

  root.replaceChildren(
    h("div", { class: "auth-wrap" },
      h("div", { class: "auth-card" },
        h("div", { class: "auth-head" },
          h("div", { class: "brand" }, brandMark(), h("span", { text: "ABIET" })),
          h("p", { class: "muted", text: "Ask your databases questions in plain English." })),
        h("div", { class: "card" },
          h("div", { class: "card-body stack" },
            info.allow_registration ? h("div", { class: "tabs", role: "tablist" }, loginTab, registerTab) : null,
            form)),
        h("p", { class: "muted small", style: { textAlign: "center", marginTop: "14px" }, text: `Version ${info.version}` }))),
  );
  setMode("login");
  username.focus();
}
