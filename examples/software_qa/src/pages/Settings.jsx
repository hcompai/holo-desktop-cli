import { useAuth } from "../auth.jsx";

export default function Settings() {
  const { user } = useAuth();
  return (
    <div>
      <h2>Settings</h2>
      <div className="panel">
        <h3>Profile</h3>
        <dl className="settings-list">
          <dt>Email</dt>
          <dd>{user}</dd>
          <dt>Workspace</dt>
          <dd>Nimbus Desk Demo</dd>
          <dt>Plan</dt>
          <dd>Team (demo)</dd>
          <dt>Notifications</dt>
          <dd>Email on ticket assignment</dd>
        </dl>
      </div>
    </div>
  );
}
