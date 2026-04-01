import React, { useState, useMemo } from 'react';
import { Button } from '../ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '../ui/command';
import { Plus, X, Check } from 'lucide-react';
import { OptimizedSiteCombobox, OptimizedStaffCombobox } from '../SelectionComponents';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { cn } from '../../lib/utils';
import { RadioGroup, RadioGroupItem } from '../ui/radio-group';
import { Label } from '../ui/label';

const FILTER_FIELDS = {
  user_id: { label: 'Staff', type: 'staff' },
  site_id: { label: 'Site', type: 'site' },
  division: { label: 'Division', type: 'division' },
  region: { label: 'Region', type: 'region' }
};

const OPERATORS = [
  { value: 'is', label: 'is' },
  { value: 'is_not', label: 'is not' },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'does not contain' }
];

export const DynamicFilter = ({
  activeFilters,
  onChange,
  fieldsContext // { users: [], sites: [], divisions: [], regions: [] }
}) => {
  const [addOpen, setAddOpen] = useState(false);
  const [editingFilter, setEditingFilter] = useState(null); // { id, field, operator, value }

  const addFilter = (fieldKey) => {
    const newFilter = {
      id: Math.random().toString(36).substr(2, 9),
      field: fieldKey,
      operator: 'contains',
      value: 'all'
    };
    setEditingFilter(newFilter);
    setAddOpen(false);
  };

  const removeFilter = (id) => {
    onChange(activeFilters.filter(f => f.id !== id));
  };

  const applyActiveFilter = () => {
    if (!editingFilter) return;
    
    const existingIndex = activeFilters.findIndex(f => f.id === editingFilter.id);
    if (existingIndex > -1) {
      const newFilters = [...activeFilters];
      newFilters[existingIndex] = editingFilter;
      onChange(newFilters);
    } else {
      onChange([...activeFilters, editingFilter]);
    }
    setEditingFilter(null);
  };

  const renderValueInput = () => {
    if (!editingFilter) return null;
    const fieldConfig = FILTER_FIELDS[editingFilter.field];
    
    switch (fieldConfig.type) {
      case 'staff':
        return (
          <div className="mt-4">
            <OptimizedStaffCombobox
              users={fieldsContext.users}
              value={editingFilter.value}
              onChange={(val) => setEditingFilter({ ...editingFilter, value: val })}
              isLoading={fieldsContext.users.length === 0}
            />
          </div>
        );
      case 'site':
        return (
          <div className="mt-4">
            <OptimizedSiteCombobox
              sites={fieldsContext.sites}
              value={editingFilter.value}
              onChange={(val) => setEditingFilter({ ...editingFilter, value: val })}
              isLoading={fieldsContext.sites.length === 0}
            />
          </div>
        );
      case 'division':
        return (
          <div className="mt-4">
            <Select 
              value={editingFilter.value} 
              onValueChange={(val) => setEditingFilter({ ...editingFilter, value: val })}
            >
              <SelectTrigger className="w-full bg-transparent border-slate-700 hover:bg-slate-800/50">
                <SelectValue placeholder="Select Division" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Divisions</SelectItem>
                {fieldsContext.divisions.map(d => (
                  <SelectItem key={d} value={d}>{d}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        );
      case 'region':
        return (
          <div className="mt-4">
            <Select 
              value={editingFilter.value} 
              onValueChange={(val) => setEditingFilter({ ...editingFilter, value: val })}
            >
              <SelectTrigger className="w-full bg-transparent border-slate-700 hover:bg-slate-800/50">
                <SelectValue placeholder="Select Region" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Regions</SelectItem>
                {fieldsContext.regions.map(r => (
                  <SelectItem key={r} value={r}>{r}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        );
      case 'text':
        return (
          <div className="mt-4">
            <input
              type="text"
              className="w-full h-10 px-3 py-2 bg-transparent border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/20 text-slate-900"
              placeholder={`Enter ${FILTER_FIELDS[editingFilter.field].label.toLowerCase()}...`}
              value={editingFilter.value === 'all' ? '' : editingFilter.value}
              onChange={(e) => setEditingFilter({ ...editingFilter, value: e.target.value })}
              autoFocus
            />
          </div>
        );
      default:
        return null;
    }
  };

  const getLabelForValue = (filter) => {
    if (!filter.value || filter.value === 'all') return 'any';
    
    if (filter.field === 'user_id') {
      const user = fieldsContext.users.find(u => u.id === filter.value);
      return user ? user.username : filter.value;
    }
    if (filter.field === 'site_id') {
      const site = fieldsContext.sites.find(s => s.id === filter.value);
      return site ? site.name : filter.value;
    }
    return filter.value;
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {activeFilters.map(filter => (
        <Popover key={filter.id} open={editingFilter?.id === filter.id} onOpenChange={(open) => !open && setEditingFilter(null)}>
          <PopoverTrigger asChild>
            <div 
              className="flex items-center bg-slate-100 hover:bg-slate-200 text-slate-900 border border-slate-300 rounded-full px-3 py-1 text-sm shadow-sm cursor-pointer transition-colors"
              onClick={() => setEditingFilter(filter)}
            >
              <span className="font-semibold">{FILTER_FIELDS[filter.field]?.label}</span>
              <span className="mx-1 text-slate-500 font-normal">:</span>
              <span className="font-semibold truncate max-w-[150px]">{getLabelForValue(filter)}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeFilter(filter.id);
                }}
                className="ml-2 p-0.5 hover:bg-slate-300 rounded-full text-slate-500 hover:text-slate-800"
              >
                <X size={14} />
              </button>
            </div>
          </PopoverTrigger>
          {editingFilter?.id === filter.id && (
            <PopoverContent className="w-[300px] p-4 bg-white border border-slate-200 shadow-xl rounded-xl z-[100]" align="start">
              <div className="space-y-4">
                 <div className="pt-2">
                    {renderValueInput()}
                 </div>

                 <div className="pt-4 flex justify-between gap-3">
                    <Button variant="ghost" className="flex-1 text-slate-500" onClick={() => setEditingFilter(null)}>Cancel</Button>
                    <Button className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white" onClick={applyActiveFilter}>Apply Filter</Button>
                 </div>
              </div>
            </PopoverContent>
          )}
        </Popover>
      ))}

      {/* + Add Filter Popover */}
      <Popover open={addOpen || (editingFilter && !activeFilters.find(f => f.id === editingFilter.id))} onOpenChange={(open) => {
        if (!open) {
          setAddOpen(false);
          if (editingFilter && !activeFilters.find(f => f.id === editingFilter.id)) {
            setEditingFilter(null);
          }
        }
      }}>
        <PopoverTrigger asChild>
          <Button 
            variant="ghost" 
            size="icon" 
            className={cn(
              "rounded-md w-9 h-9 border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 shadow-sm",
              (addOpen || (editingFilter && !activeFilters.find(f => f.id === editingFilter.id))) && "ring-2 ring-indigo-500/20"
            )}
            onClick={() => setAddOpen(true)}
          >
            <Plus size={20} />
          </Button>
        </PopoverTrigger>
        
        {(addOpen || (editingFilter && !activeFilters.find(f => f.id === editingFilter.id))) && (
          <PopoverContent 
            className={cn(
              "p-0 overflow-hidden bg-white border border-slate-200 shadow-xl rounded-xl flex transition-all duration-200 ease-in-out",
              editingFilter ? "w-[500px]" : "w-[200px]"
            )} 
            align="start"
          >
            {/* Left Side: Field Selection */}
            <div className={cn("w-[200px] bg-slate-50/50", editingFilter && "border-r border-slate-100")}>
              <Command className="bg-transparent">
                <CommandList className="max-h-[300px] overflow-auto p-1">
                  <CommandGroup>
                    {Object.entries(FILTER_FIELDS).map(([key, config]) => (
                      <CommandItem
                        key={key}
                        onSelect={() => addFilter(key)}
                        className={cn(
                          "px-3 py-2 rounded-md cursor-pointer flex items-center text-sm transition-colors",
                          editingFilter?.field === key ? "bg-indigo-50 text-indigo-700 font-medium" : "hover:bg-slate-100 text-slate-700"
                        )}
                      >
                        {config.label}
                        {editingFilter?.field === key && <Check className="ml-auto w-4 h-4" />}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </div>

            {/* Right Side: Value Input (only if a field is selected) */}
            {editingFilter && (
              <div className="flex-1 p-4 bg-white animate-in fade-in slide-in-from-left-2 duration-200">
                <div className="space-y-4">
                  <div className="text-sm font-medium text-slate-900 border-b border-slate-50 pb-2">
                    Filter by {FILTER_FIELDS[editingFilter.field].label}
                  </div>
                  
                  <div className="min-h-[60px]">
                    {renderValueInput()}
                  </div>

                  <div className="pt-4 flex justify-end gap-3 border-t border-slate-50">
                    <Button 
                      variant="ghost" 
                      size="sm"
                      className="text-slate-500 hover:text-slate-800 font-medium" 
                      onClick={() => setEditingFilter(null)}
                    >
                      Cancel
                    </Button>
                    <Button 
                      size="sm"
                      className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium shadow-sm px-4" 
                      onClick={applyActiveFilter}
                    >
                      Apply Filter
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </PopoverContent>
        )}
      </Popover>
      
      {activeFilters.length > 0 && (
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={() => onChange([])}
          className="text-slate-500 hover:text-slate-800 h-9 ml-1 text-xs font-medium"
        >
          Clear filters
        </Button>
      )}
    </div>
  );
};
