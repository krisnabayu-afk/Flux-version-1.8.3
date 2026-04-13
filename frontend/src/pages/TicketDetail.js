import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

// Modular Components
import { TicketHeader } from '../components/ticket-detail/TicketHeader';
import { TicketDetailsCard } from '../components/ticket-detail/TicketDetailsCard';
import { LinkedReportCard } from '../components/ticket-detail/LinkedReportCard';
import { CommentsSection } from '../components/ticket-detail/CommentsSection';
import { TicketActions } from '../components/ticket-detail/TicketActions';
import { TicketDialogs } from '../components/ticket-detail/TicketDialogs';

const API = `${process.env.REACT_APP_API_URL}/api`;


const TicketDetail = () => {
  const { ticketId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [ticket, setTicket] = useState(null);
  const [comment, setComment] = useState('');

  const [showEditDialog, setShowEditDialog] = useState(false);


  const [sites, setSites] = useState([]);
  const [linkedReport, setLinkedReport] = useState(null);
  const [loading, setLoading] = useState(true);


  const [editForm, setEditForm] = useState({
    title: '',
    description: '',
    priority: '',
    assigned_to_division: '',
    site_id: undefined,
    ticket_number: '',
    category: ''
  });

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchTicket(), fetchSites()]);
      setLoading(false);
    };
    init();
  }, [ticketId]);



  const fetchTicket = async () => {
    try {
      const response = await axios.get(`${API}/tickets/${ticketId}`);
      setTicket(response.data);
      if (response.data.linked_report_id) {
        try {
          const reportRes = await axios.get(`${API}/reports/${response.data.linked_report_id}`);
          setLinkedReport(reportRes.data);
        } catch (reportError) {
          console.error('Failed to fetch linked report:', reportError);
          if (reportError.response?.status === 404) {
            toast.error('Linked report not found');
          }
        }
      }
    } catch (error) {
      toast.error('Failed to load ticket');
    }
  };



  const fetchSites = async () => {
    try {
      const response = await axios.get(`${API}/sites`, { params: { limit: 1000 } });
      setSites(response.data.items || response.data);
    } catch (error) {
      console.error('Failed to fetch sites:', error);
    }
  };

  const handleAddComment = async (e) => {
    e.preventDefault();
    if (!comment.trim()) return;
    try {
      await axios.post(`${API}/tickets/${ticketId}/comments`, { ticket_id: ticketId, comment });
      toast.success('Comment added');
      setComment('');
      fetchTicket();
    } catch (error) {
      toast.error('Failed to add comment');
    }
  };



  const handleCloseTicket = async () => {
    try {
      await axios.post(`${API}/tickets/${ticketId}/close`);
      toast.success('Ticket closed!');
      fetchTicket();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Cannot close ticket');
    }
  };

  const handleDeleteTicket = async () => {
    if (!window.confirm('Are you sure you want to delete this ticket? This action cannot be undone.')) {
      return;
    }

    try {
      await axios.delete(`${API}/tickets/${ticketId}`);
      toast.success('Ticket deleted successfully');
      navigate('/tickets');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete ticket');
    }
  };

  const handleStatusChange = async (newStatus) => {
    try {
      await axios.patch(`${API}/tickets/${ticketId}`, { status: newStatus });
      toast.success('Status updated');
      fetchTicket();
    } catch (error) {
      toast.error('Failed to update status');
    }
  };

  const handleEditTicket = () => {
    setEditForm({
      title: ticket.title,
      description: ticket.description,
      assigned_to_division: ticket.assigned_to_division,
      site_id: ticket.site_id || undefined,
      ticket_number: ticket.ticket_number || '',
      category: ticket.category || ''
    });
    setShowEditDialog(true);
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.put(`${API}/tickets/${ticketId}`, editForm);
      toast.success('Ticket updated!');
      setShowEditDialog(false);
      fetchTicket();
    } catch (error) {
      toast.error('Failed to update ticket');
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      'INTERNAL': 'bg-slate-100 text-slate-800 dark:bg-gray-700/50 dark:text-gray-300',
      'PENJADWALAN': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
      'BRIEFING': 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
      'DISPATCH': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
      'FIBERZONE': 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
      'DONE': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
      'Open': 'bg-slate-100 text-slate-800 dark:bg-gray-700/50 dark:text-gray-300',
      'In Progress': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
      'Closed': 'bg-slate-200 text-slate-600 dark:bg-gray-800 dark:text-gray-400'
    };
    return colors[status] || 'bg-secondary text-muted-foreground';
  };

  if (loading || !ticket) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-lg text-muted-foreground">Loading ticket details...</div>
      </div>
    );
  }

  const canManage = !!user?.role;
  const canEdit = user?.role ? true : false;
  const canClose = user?.role && ticket.status !== 'Closed';
  const canDelete = ['Admin', 'SuperUser', 'Manager', 'VP'].includes(user?.role);
  const isCloseDisabled = ticket.linked_report_id && linkedReport?.status !== 'Final';

  return (
    <div className="space-y-6" data-testid="ticket-detail-page">
      <TicketHeader
        ticket={ticket}
        navigate={navigate}
        getStatusColor={getStatusColor}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <TicketDetailsCard ticket={ticket} />

          <LinkedReportCard linkedReport={linkedReport} />

          <CommentsSection
            ticket={ticket}
            comment={comment}
            setComment={setComment}
            handleAddComment={handleAddComment}
          />
        </div>

        <TicketActions
          ticket={ticket}
          canManage={canManage}
          canEdit={canEdit}
          canClose={canClose}
          canDelete={canDelete}
          isCloseDisabled={isCloseDisabled}
          handleStatusChange={handleStatusChange}
          handleEditTicket={handleEditTicket}
          handleCloseTicket={handleCloseTicket}
          handleDeleteTicket={handleDeleteTicket}
        />
      </div>

      <TicketDialogs
        ticket={ticket}
        showEditDialog={showEditDialog}
        setShowEditDialog={setShowEditDialog}
        editForm={editForm}
        setEditForm={setEditForm}
        handleEditSubmit={handleEditSubmit}
        sites={sites}
      />
    </div>
  );
};

export default TicketDetail;
