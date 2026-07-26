import { Link } from "react-router-dom";
import { useAuth } from "../context/auth.js";

/** Approved users with prediction access. */
export default function ApprovedRoute({ children }) {
  const { profile } = useAuth();
  const status = profile?.status;

  if (status === "pending") {
    return (
      <div className="mx-auto max-w-lg rounded-lg border border-amber-700/50 bg-amber-950/30 p-6 text-center">
        <h2 className="mb-2 text-lg font-semibold text-amber-200">Waiting for approval</h2>
        <p className="mb-4 text-sm text-amber-100/80">
          Your account is registered but an admin must approve it before you can run predictions.
          You can still view your feedback history.
        </p>
        <Link to="/feedback" className="text-sky-400 text-sm hover:underline">
          Go to My feedback
        </Link>
      </div>
    );
  }

  if (status === "banned") {
    return (
      <div className="rounded-lg border border-red-800 bg-red-950/40 p-6 text-center text-red-200">
        Your account is suspended. Contact support.
      </div>
    );
  }

  return children;
}
