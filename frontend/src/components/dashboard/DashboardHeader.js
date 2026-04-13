import React from 'react';

export const DashboardHeader = ({ user }) => {
    return (
        <div className="mb-2">
            <h1 className="text-4xl font-extrabold text-slate-800 tracking-tight">
                Welcome back, {user?.first_name && user?.last_name ? `${user.first_name} ${user.last_name}` : user?.username}!
            </h1>
        </div>
    );
};
