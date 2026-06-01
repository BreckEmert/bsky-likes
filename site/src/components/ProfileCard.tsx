import { useProfile } from "../lib/useProfile.ts";

interface Props {
  handle: string | null;
}

function compact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K";
  return String(n);
}

// Floating profile card for the currently-selected handle. Search-triggered for
// now; the same component will back hover on the dot/scatter plots later.
export function ProfileCard({ handle }: Props) {
  const { profile, loading } = useProfile(handle);
  if (!handle) return null;

  return (
    <a
      className="profilecard"
      href={`https://bsky.app/profile/${handle}`}
      target="_blank"
      rel="noopener noreferrer"
      title="open on Bluesky"
    >
      {loading ? (
        <div className="profilecard__loading">loading @{handle}…</div>
      ) : !profile ? (
        <div className="profilecard__loading">@{handle} (no profile)</div>
      ) : (
        <>
          <div className="profilecard__top">
            {profile.avatar ? (
              <img className="profilecard__avatar" src={profile.avatar} alt="" />
            ) : (
              <div className="profilecard__avatar profilecard__avatar--blank" />
            )}
            <div className="profilecard__id">
              <div className="profilecard__name">{profile.displayName}</div>
              <div className="profilecard__handle">@{profile.handle}</div>
            </div>
          </div>
          {profile.description && (
            <div className="profilecard__desc">{profile.description}</div>
          )}
          <div className="profilecard__stats">
            <span>
              <b>{compact(profile.followersCount)}</b> followers
            </span>
            <span>
              <b>{compact(profile.followsCount)}</b> following
            </span>
          </div>
        </>
      )}
    </a>
  );
}
