import React, { useState } from "react";
import { Loader2, Eye, EyeOff } from "lucide-react";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const credentials = btoa(`${username}:${password}`);
      const res = await fetch("/api/login", {
        headers: {
          Authorization: `Basic ${credentials}`,
        },
      });

      if (res.ok) {
        localStorage.setItem("auth_credentials", credentials);
        onLogin();
      } else {
        setError("Invalid username or password");
      }
    } catch (err) {
      setError("An error occurred while signing in");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-zinc-900 border-2 border-zinc-800 rounded-3xl p-8 shadow-2xl">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-black tracking-tight text-lime-400 mb-2">
            Bill Express
          </h1>
          <p className="text-zinc-400 font-bold uppercase tracking-wider text-sm">
            Sign in to your account
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="bg-rose-500/10 border-2 border-rose-500 rounded-xl p-4 text-rose-500 font-bold text-center text-sm">
              {error}
            </div>
          )}

          <div>
            <label
              htmlFor="username"
              className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2"
            >
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              disabled={isLoading}
              onChange={(e) => setUsername(e.target.value)}
              className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              placeholder="Enter username"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-bold text-zinc-400 uppercase tracking-wider mb-2"
            >
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                disabled={isLoading}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full bg-zinc-950 border-2 border-zinc-800 rounded-xl px-4 py-3 text-white focus:ring-0 focus:border-lime-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed pr-12"
                placeholder="Enter password"
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-white transition-colors"
                onClick={() => setShowPassword(!showPassword)}
                disabled={isLoading}
                aria-label={showPassword ? "Hide password" : "Show password"}
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full flex justify-center items-center py-4 px-4 border-2 border-zinc-950 rounded-xl shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] text-lg font-black text-zinc-950 bg-lime-400 hover:bg-lime-300 hover:translate-y-[-2px] hover:translate-x-[-2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:translate-x-0 disabled:hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-all uppercase tracking-wider mt-8"
          >
            {isLoading ? (
              <>
                <Loader2 className="animate-spin h-6 w-6 mr-2" />
                Signing In...
              </>
            ) : (
              "Sign In"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
