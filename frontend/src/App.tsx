import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Contacts from './pages/Contacts';
import ContactDetail from './pages/ContactDetail';
import Groups from './pages/Groups';
import GroupDetail from './pages/GroupDetail';
import Reviews from './pages/Reviews';
import Analyses from './pages/Analyses';
import Messages from './pages/Messages';
import Scheduler from './pages/Scheduler';
import Settings from './pages/Settings';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/contacts" element={<Contacts />} />
          <Route path="/contacts/:wxid" element={<ContactDetail />} />
          <Route path="/groups" element={<Groups />} />
          <Route path="/groups/:groupId" element={<GroupDetail />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/reviews" element={<Reviews />} />
          <Route path="/analyses" element={<Analyses />} />
          <Route path="/scheduler" element={<Scheduler />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
