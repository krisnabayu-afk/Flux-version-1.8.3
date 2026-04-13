import { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { toast } from 'sonner';
import { Plus, Search, ArrowUpDown, Pencil, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';
import SiteCombobox from '../components/SiteCombobox';
import { DynamicFilter } from '../components/DynamicFilter';
import { SearchableSelectCombobox } from '../components/SelectionComponents';

const API = `${process.env.REACT_APP_API_URL}/api`;

const Tickets = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tickets, setTickets] = useState([]);
  const [sites, setSites] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeFilters, setActiveFilters] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState('newest');
  const [conditionFilter, setConditionFilter] = useState('all'); // 'all', 'open' or 'closed'
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    assigned_to_division: 'Monitoring',
    site_id: undefined,
    ticket_number: '',
    category: ''
  });
  const [departments, setDepartments] = useState([]);

  const TICKET_FILTER_FIELDS = useMemo(() => ({
    category: { 
      label: 'Category', 
      type: 'select', 
      options: ['FOKMON', 'MAINTENANCE', 'WO BOD/UPGRADE', 'FYI', 'DOWN', 'RFO', 'FIBERZONE', 'VLEPO', 'FTTR', 'MEGALOS', 'EMAIL', 'INTERNET', 'ACCESS POINT', 'VIRTUAL', 'DEVICE', 'REPORT', 'REQUEST CLIENT'] 
    },
    site_id: { label: 'Site', type: 'site' },
    region: { label: 'Region', type: 'select', options: ['Region 1', 'Region 2', 'Region 3'] },
    status: { 
      label: 'Status', 
      type: 'select', 
      options: ['INTERNAL', 'PENJADWALAN', 'BRIEFING', 'DISPATCH', 'FIBERZONE', 'DONE'] 
    },
    assigned_to_division: { 
      label: 'Assign To', 
      type: 'select', 
      options: [
        ...(user?.department === 'Technical Operation' ? ['Infra & Fiberzone', 'TS & Apps'] : []),
        ...departments.flatMap(d => d.divisions).filter((v, i, a) => a.indexOf(v) === i).sort()
      ]
    }
  }), [departments]);

  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalTickets, setTotalTickets] = useState(0);
  const itemsPerPage = 15;

  useEffect(() => {
    fetchSites();
    fetchDepartments();
  }, []);

  const fetchDepartments = async () => {
    try {
      const response = await axios.get(`${API}/departments`);
      setDepartments(response.data);
    } catch (error) {
      console.error('Failed to fetch departments:', error);
    }
  };

  // Reset to page 1 when filters or search change
  useEffect(() => {
    setCurrentPage(1);
  }, [activeFilters, searchQuery, conditionFilter]);

  useEffect(() => {
    fetchTickets(currentPage);
  }, [currentPage, activeFilters, searchQuery, conditionFilter]);

  // Helper to determine ticket age color
  const getTicketAgeColor = (createdAt, status) => {
    if (status === 'Closed') return 'hover:bg-muted/50';

    const createdDate = new Date(createdAt);
    const now = new Date();
    const diffInHours = (now - createdDate) / (1000 * 60 * 60);

    if (diffInHours < 1) return 'bg-blue-500/5 hover:bg-blue-500/10 border-l-4 border-l-blue-500';
    if (diffInHours < 3) return 'bg-yellow-500/5 hover:bg-yellow-500/10 border-l-4 border-l-yellow-500';
    return 'bg-red-500/5 hover:bg-red-500/10 border-l-4 border-l-red-500';
  };

  const handleDeleteTicket = async (ticketId) => {
    if (!window.confirm('Are you sure you want to delete this ticket? This action cannot be undone.')) {
      return;
    }

    try {
      await axios.delete(`${API}/tickets/${ticketId}`);
      toast.success('Ticket deleted successfully');
      fetchTickets(currentPage);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete ticket');
    }
  };

  const fetchTickets = async (page = 1) => {
    try {
      const params = {
        page,
        limit: itemsPerPage
      };
      
      if (searchQuery) params.search = searchQuery;
      
      // Apply condition filter (open vs closed vs all)
      if (conditionFilter === 'closed') {
        params.status = 'Closed';
      } else if (conditionFilter === 'open') {
        params.exclude_closed = true;
      }
      
      // Apply active filters to params
      activeFilters.forEach(filter => {
        if (filter.value && filter.value !== 'all') {
          // If user picks a specific status filter, override the condition filter
          if (filter.field === 'status') {
            params.status = filter.value;
            delete params.exclude_closed;
          } else {
            params[filter.field] = filter.value;
          }
        }
      });

      const response = await axios.get(`${API}/tickets`, { params });

      if (response.data.items) {
        setTickets(response.data.items);
        setTotalPages(response.data.total_pages);
        setTotalTickets(response.data.total);
      } else {
        setTickets(response.data);
      }
    } catch (error) {
      console.error('Failed to fetch tickets:', error);
    }
  };

  const fetchSites = async () => {
    try {
      const response = await axios.get(`${API}/sites`, { params: { limit: 1000 } });
      if (response.data.items) {
        setSites(response.data.items);
      } else {
        setSites(response.data);
      }
    } catch (error) {
      console.error('Failed to fetch sites:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      await axios.post(`${API}/tickets`, formData);
      toast.success('Ticket created successfully!');
      setOpen(false);
      fetchTickets(currentPage);
      setFormData({
        title: '',
        description: '',
        assigned_to_division: 'Monitoring',
        site_id: undefined,
        ticket_number: '',
        category: ''
      });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create ticket');
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      'INTERNAL': 'bg-slate-100 text-slate-800 dark:bg-gray-700/50 dark:text-gray-300 border-transparent dark:border-gray-600',
      'PENJADWALAN': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border-transparent border-blue-800',
      'BRIEFING': 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 border-transparent border-purple-800',
      'DISPATCH': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 border-transparent dark:border-yellow-800',
      'FIBERZONE': 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300 border-transparent border-orange-800',
      'DONE': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 border-transparent border-green-800',
      'Open': 'bg-slate-100 text-slate-800 dark:bg-gray-700/50 dark:text-gray-300 border-transparent dark:border-gray-600',
      'In Progress': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 border-transparent dark:border-yellow-800',
      'Closed': 'bg-slate-200 text-slate-600 dark:bg-gray-800 dark:text-gray-400 border-transparent dark:border-gray-700'
    };
    return colors[status] || 'bg-secondary text-muted-foreground';
  };

  const getDivisionColor = (division) => {
    const colors = {
      'Monitoring': 'bg-blue-500',
      'Infra': 'bg-purple-500',
      'TS': 'bg-green-500',
      'Internal Support': 'bg-cyan-500'
    };
    return colors[division] || 'bg-gray-500';
  };

  return (
    <div className="space-y-6" data-testid="tickets-page">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold text-foreground mb-2">Ticket Management</h1>
          <p className="text-muted-foreground">Track and manage support tickets</p>
        </div>

        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="bg-red-500 hover:bg-red-600" data-testid="create-ticket-button">
              <Plus size={18} className="mr-2" />
              Create Ticket
            </Button>
          </DialogTrigger>
          <DialogContent data-testid="ticket-dialog" className="bg-card border-border text-foreground" onCloseAutoFocus={(e) => e.preventDefault()}>
            <DialogHeader>
              <DialogTitle className="text-foreground">Create New Ticket</DialogTitle>
              <DialogDescription className="text-muted-foreground">Fill in the details to create a new support ticket.</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="flex flex-col h-full max-h-[85vh]">
              <div className="flex-1 overflow-y-auto pr-2 space-y-4 custom-scrollbar">
                <div className="space-y-2">
                  <Label htmlFor="title" className="text-foreground">Title</Label>
                  <Input
                    id="title"
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                    required
                    data-testid="ticket-title-input"
                    className="bg-background border-input text-foreground"
                    placeholder="VLEPO/Internet/Waas Issue - Site X - 20/11/2025"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="ticket_number" className="text-foreground">Ticket Number</Label>
                    <Input
                      id="ticket_number"
                      value={formData.ticket_number}
                      onChange={(e) => setFormData({ ...formData, ticket_number: e.target.value })}
                      data-testid="ticket-number-input"
                      className="bg-background border-input text-foreground"
                      placeholder="Ticket# or URL (http...)"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label className="text-foreground">Category</Label>
                    <SearchableSelectCombobox
                      options={TICKET_FILTER_FIELDS.category.options}
                      value={formData.category}
                      onChange={(value) => setFormData({ ...formData, category: value })}
                      placeholder="Select Category"
                      emptyText="No category found."
                      className="bg-background"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="site" className="text-foreground">Site Name</Label>
                    <SiteCombobox
                      sites={sites}
                      value={formData.site_id}
                      onChange={(val) => setFormData({ ...formData, site_id: val })}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label className="text-foreground">Assign To Division</Label>
                    <Select value={formData.assigned_to_division} onValueChange={(value) => setFormData({ ...formData, assigned_to_division: value })}>
                      <SelectTrigger className="bg-background border-input text-foreground" data-testid="division-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-popover border-border text-popover-foreground">
                        {TICKET_FILTER_FIELDS.assigned_to_division.options.map(opt => (
                          <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="description" className="text-foreground">Description</Label>
                  <Textarea
                    id="description"
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    required
                    data-testid="ticket-description-input"
                    className="bg-background border-input text-foreground min-h-[100px]"
                    placeholder="Detail issue di site"
                    rows={4}
                  />
                </div>
              </div>

              <div className="flex justify-end space-x-2 pt-6 mt-4 border-t border-border/50">
                <Button type="button" variant="outline" onClick={() => setOpen(false)} className="border-border text-muted-foreground hover:bg-accent font-medium">
                  Cancel
                </Button>
                <Button type="submit" className="bg-red-500 hover:bg-red-600 px-6 font-semibold shadow-lg shadow-red-500/20" data-testid="submit-ticket-button">
                  Create Ticket
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 py-4">
        {/* Left: Dynamic Filters */}
        <div className="flex-1">
          <DynamicFilter 
            activeFilters={activeFilters}
            onChange={setActiveFilters}
            filterFields={TICKET_FILTER_FIELDS}
            fieldsContext={{ sites }}
          />
        </div>

        {/* Right: Condition Toggle + Search & Sort */}
        <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
          {/* Open / Closed / All Toggle */}
          <div className="flex items-center gap-0.5 bg-muted/50 p-0.5 rounded-lg">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConditionFilter('all')}
              className={cn(
                'h-7 px-3 rounded-md text-xs font-medium transition-all',
                conditionFilter === 'all'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              All
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConditionFilter('open')}
              className={cn(
                'h-7 px-3 rounded-md text-xs font-medium transition-all',
                conditionFilter === 'open'
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              Open
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConditionFilter('closed')}
              className={cn(
                'h-7 px-3 rounded-md text-xs font-medium transition-all',
                conditionFilter === 'closed'
                  ? 'bg-slate-600 text-white shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              Closed
            </Button>
          </div>

          <div className="relative w-full md:w-64">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search tickets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-background border-input hover:border-ring focus:border-primary rounded-full transition-colors text-foreground h-9"
            />
          </div>

          <Select value={sortOrder} onValueChange={setSortOrder}>
            <SelectTrigger className="w-[150px] bg-background border-input rounded-lg hover:bg-accent text-foreground h-9">
              <div className="flex items-center gap-2">
                <ArrowUpDown size={14} className="text-muted-foreground" />
                <SelectValue />
              </div>
            </SelectTrigger>
            <SelectContent className="bg-popover border-border text-popover-foreground">
              <SelectItem value="newest">Newest First</SelectItem>
              <SelectItem value="oldest">Oldest First</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Tickets Table View */}
      <div className="rounded-md border border-border bg-card overflow-hidden">
        <Table>
          <TableHeader className="bg-muted/50 sticky top-0 z-10">
            <TableRow className="hover:bg-muted/50 border-b border-border">
              <TableHead className="w-[180px] text-muted-foreground font-medium">Ticket Number</TableHead>
              <TableHead className="w-[180px] text-muted-foreground font-medium">Ticket Name</TableHead>
              <TableHead className="text-muted-foreground font-medium">Category</TableHead>
              <TableHead className="text-muted-foreground font-medium">Site</TableHead>
              <TableHead className="text-muted-foreground font-medium">Regional</TableHead>
              <TableHead className="text-muted-foreground font-medium">Assign To</TableHead>
              <TableHead className="text-muted-foreground font-medium">Date</TableHead>
              <TableHead className="text-muted-foreground font-medium">Status</TableHead>
              <TableHead className="text-right text-muted-foreground font-medium pr-6">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tickets.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                  No tickets match your filters
                </TableCell>
              </TableRow>
            ) : (
              tickets.map((ticket) => (
                <TableRow
                  key={ticket.id}
                  className={cn(
                    "border-b border-border group transition-colors",
                    getTicketAgeColor(ticket.created_at, ticket.status)
                  )}
                >
                  <TableCell className="font-medium">
                    {ticket.ticket_number && (ticket.ticket_number.startsWith('http://') || ticket.ticket_number.startsWith('https://')) ? (
                      <a href={ticket.ticket_number} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                        View Link
                      </a>
                    ) : (
                      ticket.ticket_number || '-'
                    )}
                  </TableCell>
                  <TableCell className="font-medium">
                    <div
                      onClick={() => navigate(`/tickets/${ticket.id}`)}
                      className="flex items-center space-x-2 cursor-pointer hover:underline text-foreground"
                    >
                      <span className="font-bold text-primary truncate max-w-[150px]">{ticket.title}</span>
                    </div>
                    {ticket.description && (
                      <p className="text-xs text-muted-foreground truncate max-w-[150px] mt-1">
                        {ticket.description}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="text-foreground">
                    {ticket.category || '-'}
                  </TableCell>
                  <TableCell className="text-foreground">
                    {ticket.site_name || '-'}
                  </TableCell>
                  <TableCell className="text-foreground">
                    {ticket.region || ticket.site_region || '-'}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={cn("font-normal border-transparent text-white", getDivisionColor(ticket.assigned_to_division))}>
                      {ticket.assigned_to_division}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    <div>{new Date(ticket.created_at).toLocaleDateString()}</div>
                    <div className="text-xs opacity-70">{new Date(ticket.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                  </TableCell>
                  <TableCell>
                    <Badge className={cn("min-w-[80px] justify-center shadow-none text-[10px] py-0 h-5", getStatusColor(ticket.status))}>
                      {ticket.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right pr-6">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/tickets/${ticket.id}`);
                        }}
                        className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                        title="Edit Ticket"
                      >
                        <Pencil size={16} />
                      </Button>
                      {(['Admin', 'SuperUser', 'Manager', 'VP'].includes(user.role)) && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteTicket(ticket.id);
                          }}
                          className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                          title="Delete Ticket"
                        >
                          <Trash2 size={16} />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination Controls */}
      {totalTickets > 0 && (
        <div className="flex items-center justify-between py-4">
          <div className="text-sm text-muted-foreground">
            Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, totalTickets)} of {totalTickets} tickets
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
              disabled={currentPage === 1}
            >
              Previous
            </Button>
            <div className="text-sm font-medium">
              Page {currentPage} of {totalPages}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
              disabled={currentPage === totalPages}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div >
  );
};

export default Tickets;
