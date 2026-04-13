import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Button } from '../ui/button';
import { Edit, CheckCircle, Trash2 } from 'lucide-react';

export const TicketActions = ({
    ticket,
    canManage,
    canEdit,
    canClose,
    isCloseDisabled,
    handleStatusChange,
    handleEditTicket,

    handleCloseTicket,
    handleDeleteTicket,
    canDelete
}) => {
    return (
        <div className="space-y-6">
            {/* Status Management */}
            {canManage && ticket.status !== 'Closed' && (
                <Card className="bg-card border-border">
                    <CardHeader>
                        <CardTitle className="text-lg text-foreground">Manage Status</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <Select value={ticket.status} onValueChange={handleStatusChange}>
                            <SelectTrigger data-testid="status-select" className="bg-background border-input text-foreground">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-popover border-border text-popover-foreground">
                                <SelectItem value="INTERNAL">INTERNAL</SelectItem>
                                <SelectItem value="PENJADWALAN">PENJADWALAN</SelectItem>
                                <SelectItem value="BRIEFING">BRIEFING</SelectItem>
                                <SelectItem value="DISPATCH">DISPATCH</SelectItem>
                                <SelectItem value="FIBERZONE">FIBERZONE</SelectItem>
                                <SelectItem value="DONE">DONE</SelectItem>
                            </SelectContent>
                        </Select>
                    </CardContent>
                </Card>
            )}

            {/* Integration Actions */}
            <Card className="border-2 border-border bg-card">
                <CardHeader>
                    <CardTitle className="text-lg text-foreground">Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    {/* Edit Ticket Button */}
                    {canEdit && ticket.status !== 'Closed' && (
                        <Button
                            onClick={handleEditTicket}
                            className="w-full bg-secondary text-secondary-foreground hover:bg-secondary/80"
                            data-testid="edit-ticket-button"
                        >
                            <Edit size={16} className="mr-2" />
                            Edit Ticket
                        </Button>
                    )}


                    {/* Close Ticket */}
                    {canClose && (
                        <div className="space-y-2">
                            <Button
                                onClick={handleCloseTicket}
                                disabled={isCloseDisabled}
                                className="w-full bg-green-500 hover:bg-green-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
                                data-testid="close-ticket-button"
                            >
                                <CheckCircle size={16} className="mr-2" />
                                Close Ticket
                            </Button>
                            {isCloseDisabled && (
                                <p className="text-xs text-red-600 text-center">
                                    Linked report must be approved before closing
                                </p>
                            )}
                        </div>
                    )}

                    {/* Delete Ticket */}
                    {canDelete && (
                        <Button
                            onClick={handleDeleteTicket}
                            variant="destructive"
                            className="w-full bg-red-600 hover:bg-red-700 text-white"
                            data-testid="delete-ticket-button"
                        >
                            <Trash2 size={16} className="mr-2" />
                            Delete Ticket
                        </Button>
                    )}
                </CardContent>
            </Card>
        </div>
    );
};
